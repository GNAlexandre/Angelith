# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Alexandre Tournel

"""Lecture des sources .epub (`pipeline/epub.py`).

Les EPUB sont fabriqués **à la main** dans les tests, avec les particularités réellement
rencontrées sur `sources/roman A/Vol.1/JAP/roman A.epub` : spans Kobo autour de
chaque phrase, furigana `<ruby>`, illustrations en `<svg><image xlink:href>`, chapitres ouverts
par un paragraphe STYLÉ et non par une balise de titre, OPF ailleurs que dans `OEBPS/`.

Un test lit l'EPUB réel s'il est présent, et se saute sinon (comme les tests qui dépendent du
modèle ONNX côté manga) — les sources ne sont pas versionnées.
"""
from __future__ import annotations

import zipfile
from pathlib import Path

import pytest

from pipeline import epub, extract, split

REEL = Path(__file__).resolve().parents[1] / "sources/roman A/Vol.1/JAP/roman A.epub"


# --------------------------------------------------------------------------- #
# Fabrication d'EPUB de test
# --------------------------------------------------------------------------- #

CONTAINER = """<?xml version="1.0" encoding="UTF-8"?>
<container xmlns="urn:oasis:names:tc:opendocument:xmlns:container" version="1.0">
<rootfiles><rootfile full-path="{opf}" media-type="application/oebps-package+xml"/></rootfiles>
</container>"""


def _page(corps: str, lang: str = "ja") -> str:
    return (f'<?xml version="1.0" encoding="UTF-8"?><!DOCTYPE html>'
            f'<html xmlns="http://www.w3.org/1999/xhtml" xml:lang="{lang}">'
            f'<head><meta charset="UTF-8"/><title>Titre du livre</title>'
            f'<script type="text/javascript" src="../js/kobo.js"/>'
            f'<style type="text/css">.koboSpan {{ color: red }}</style></head>'
            f'<body class="p-text"><div class="main">{corps}</div></body></html>')


def _kobo(texte: str, n: int = 1) -> str:
    """Un span Kobo, comme la chaîne de production en met autour de chaque phrase."""
    return (f'<span xmlns="http://www.w3.org/1999/xhtml" class="koboSpan" '
            f'id="kobo.{n}.1">{texte}</span>')


def ecrire_epub(dossier: Path, pages: list[tuple[str, str]], *, base: str = "item",
                images: dict[str, bytes] | None = None, toc: list[tuple[str, str]] | None = None,
                nav_epub3: bool = True, nom: str = "livre.epub",
                ordre_spine: list[str] | None = None) -> Path:
    """Fabrique un EPUB. `pages` = [(identifiant, corps xhtml)], écrites dans cet ordre dans
    le zip. `ordre_spine` permet de donner au spine un ordre DIFFÉRENT de celui du zip, pour
    vérifier lequel des deux le lecteur suit."""
    chemin = dossier / nom
    prefixe = f"{base}/" if base else ""
    manifeste, spine = [], []
    with zipfile.ZipFile(chemin, "w") as z:
        z.writestr("mimetype", "application/epub+zip")
        z.writestr("META-INF/container.xml", CONTAINER.format(opf=f"{prefixe}standard.opf"))
        for ident, corps in pages:
            z.writestr(f"{prefixe}xhtml/{ident}.xhtml", _page(corps))
            manifeste.append(f'<item id="{ident}" href="xhtml/{ident}.xhtml" '
                             f'media-type="application/xhtml+xml"/>')
        for ident in (ordre_spine if ordre_spine is not None else [i for i, _ in pages]):
            spine.append(f'<itemref idref="{ident}"/>')
        for rel, donnees in (images or {}).items():
            z.writestr(f"{prefixe}{rel}", donnees)
            manifeste.append(f'<item id="img-{Path(rel).stem}" href="{rel}" '
                             f'media-type="image/jpeg"/>')
        if toc is not None:
            if nav_epub3:
                liens = "".join(f'<li><a href="xhtml/{h}.xhtml">{lab}</a></li>'
                                for h, lab in toc)
                z.writestr(f"{prefixe}nav.xhtml", _page("", "en").replace(
                    "<div class=\"main\">",
                    f'<nav epub:type="toc" id="toc"><h1>Navigation</h1><ol>{liens}</ol></nav>'
                    '<div class="main">'))
                manifeste.append('<item id="nav" href="nav.xhtml" properties="nav" '
                                 'media-type="application/xhtml+xml"/>')
            else:
                points = "".join(
                    f'<navPoint><navLabel><text>{lab}</text></navLabel>'
                    f'<content src="xhtml/{h}.xhtml"/></navPoint>' for h, lab in toc)
                z.writestr(f"{prefixe}toc.ncx",
                           f'<?xml version="1.0" encoding="UTF-8"?><ncx><navMap>{points}'
                           f'</navMap></ncx>')
                manifeste.append('<item id="ncx" href="toc.ncx" '
                                 'media-type="application/x-dtbncx+xml"/>')
        z.writestr(f"{prefixe}standard.opf",
                   f'<?xml version="1.0" encoding="UTF-8"?><package version="3.0">'
                   f'<manifest>{"".join(manifeste)}</manifest>'
                   f'<spine{" toc=\"ncx\"" if toc is not None and not nav_epub3 else ""}'
                   f' page-progression-direction="rtl">{"".join(spine)}</spine></package>')
    return chemin


JPEG = b"\xff\xd8\xff\xe0" + b"\x00" * 40 + b"\xff\xd9"


# --------------------------------------------------------------------------- #
# Le piège central : pas d'espace insérée dans du japonais
# --------------------------------------------------------------------------- #

def test_les_elements_inline_ne_sont_JAMAIS_separes_par_une_espace(tmp_path):
    """⚠ Le défaut le plus grave possible sur une source japonaise. `<span>` et `<ruby>` sont
    inline ; les joindre par une espace donne « 千 万 丈 塔 » au lieu de « 千万丈塔 ». Le
    japonais n'a pas d'espace entre les mots : ce n'est pas une coquille de mise en forme mais
    une erreur de SEGMENTATION, qui se propage jusqu'au glossaire."""
    corps = (f"<p>{_kobo('　特務機関〈', 1)}<ruby>{_kobo('八重山吹', 2)}<rt>ヤエヤマブキ</rt>"
             f"</ruby>{_kobo('〉──通称ヤエブキ機関の', 3)}<ruby>{_kobo('八', 4)}<rt>や</rt>"
             f"{_kobo('重', 5)}<rt>え</rt></ruby>{_kobo('の術師。', 6)}</p>")
    ep = ecrire_epub(tmp_path, [("p-001", corps)])
    texte = epub.extract_epub(ep, tmp_path / "media").text
    assert "特務機関〈八重山吹〉──通称ヤエブキ機関の八重の術師。" in texte
    assert " " not in texte.replace("　", ""), "aucune espace ASCII ne doit apparaître"


def test_les_sauts_de_ligne_du_source_xhtml_ne_coupent_pas_une_phrase(tmp_path):
    """Le XHTML est indenté pour la lisibilité du fichier : ces retours à la ligne sont de la
    mise en forme, pas du texte, et ne doivent ni survivre ni devenir une espace."""
    corps = "<p>" + _kobo("前半の文\n") + "\n  " + _kobo("後半の文。", 2) + "</p>"
    texte = epub.extract_epub(ecrire_epub(tmp_path, [("p-001", corps)]),
                              tmp_path / "media").text
    assert "前半の文後半の文。" in texte


def test_un_paragraphe_LATIN_replie_dans_le_source_garde_ses_espaces(tmp_path):
    """L'autre moitié de la règle, et le piège si on ne traite que le japonais : entre deux
    lettres latines le saut de ligne du fichier vaut UNE ESPACE. Sinon un EPUB anglais replié
    à 80 colonnes donnerait « theenemy » — et le pipeline lit aussi de l'anglais, de
    l'espagnol et du chinois."""
    corps = "<p>The enemy is\n    approaching from\n    the east.</p>"
    texte = epub.extract_epub(ecrire_epub(tmp_path, [("p-001", corps)]),
                              tmp_path / "media").text
    assert texte == "The enemy is approaching from the east."


def test_le_saut_de_ligne_ne_double_pas_une_espace_deja_presente(tmp_path):
    corps = "<p>deux mots \n  separes</p>"
    texte = epub.extract_epub(ecrire_epub(tmp_path, [("p-001", corps)]),
                              tmp_path / "media").text
    assert texte == "deux mots separes"


def test_un_bloc_ferme_la_ligne(tmp_path):
    corps = "<p>" + _kobo("ligne un") + "</p><p>" + _kobo("ligne deux", 2) + "</p>"
    texte = epub.extract_epub(ecrire_epub(tmp_path, [("p-001", corps)]),
                              tmp_path / "media").text
    assert texte.splitlines() == ["ligne un", "", "ligne deux"]


def test_br_coupe_la_ligne(tmp_path):
    corps = "<p>" + _kobo("avant") + "<br/>" + _kobo("apres", 2) + "</p>"
    texte = epub.extract_epub(ecrire_epub(tmp_path, [("p-001", corps)]),
                              tmp_path / "media").text
    assert texte.splitlines() == ["avant", "apres"]


# --------------------------------------------------------------------------- #
# Furigana
# --------------------------------------------------------------------------- #

RUBY = "<p><ruby>七堕<rt>ナナエ</rt></ruby>の出現を確認。</p>"


def test_les_furigana_sont_retires_par_defaut(tmp_path):
    texte = epub.extract_epub(ecrire_epub(tmp_path, [("p-001", RUBY)]),
                              tmp_path / "media").text
    assert "七堕の出現を確認。" in texte
    assert "ナナエ" not in texte


def test_le_mode_parentheses_conserve_la_lecture(tmp_path):
    texte = epub.extract_epub(ecrire_epub(tmp_path, [("p-001", RUBY)]), tmp_path / "media",
                              epub_cfg={"ruby": "parentheses"}).text
    assert "七堕(ナナエ)の出現を確認。" in texte


def test_un_ruby_a_plusieurs_paires_apparie_chaque_base_a_SA_lecture(tmp_path):
    """Une seule balise `<ruby>` peut contenir plusieurs couples base/lecture — c'est le cas
    réel de « 千万丈塔踏破儀式 » dans ce livre."""
    corps = ("<p><ruby>千万丈塔<rt>せんまんじようとう</rt>踏破儀式<rt>とうはぎしき</rt>"
             "</ruby>を開始する</p>")
    texte = epub.extract_epub(ecrire_epub(tmp_path, [("p-001", corps)]), tmp_path / "media",
                              epub_cfg={"ruby": "parentheses"}).text
    assert "千万丈塔(せんまんじようとう)踏破儀式(とうはぎしき)を開始する" in texte


def test_la_parenthese_de_repli_rp_est_toujours_retiree(tmp_path):
    """`<rp>` n'est là que pour les lecteurs sans support du ruby : la garder donnerait
    « 七堕((ナナエ)) »."""
    corps = "<p><ruby>七堕<rp>（</rp><rt>ナナエ</rt><rp>）</rp></ruby>だ</p>"
    texte = epub.extract_epub(ecrire_epub(tmp_path, [("p-001", corps)]), tmp_path / "media",
                              epub_cfg={"ruby": "parentheses"}).text
    assert "七堕(ナナエ)だ" in texte
    assert "（" not in texte


# --------------------------------------------------------------------------- #
# Bruit à écarter
# --------------------------------------------------------------------------- #

def test_les_spans_kobo_ne_laissent_aucune_trace(tmp_path):
    texte = epub.extract_epub(ecrire_epub(tmp_path, [("p-001", "<p>" + _kobo("texte") + "</p>")]),
                              tmp_path / "media").text
    assert texte == "texte"


def test_script_style_et_titre_de_page_ne_ressortent_pas(tmp_path):
    """`<title>` contient le titre du LIVRE, répété dans les 33 documents : le laisser passer
    en ferait 33 lignes parasites, et autant de faux candidats titre."""
    texte = epub.extract_epub(ecrire_epub(tmp_path, [("p-001", "<p>corps</p>")]),
                              tmp_path / "media").text
    assert texte == "corps"
    assert "Titre du livre" not in texte
    assert "kobo.js" not in texte and "color: red" not in texte


def test_le_document_de_navigation_nest_jamais_du_texte(tmp_path):
    """Recopié en clair, il injecterait la table des matières au milieu du roman — et ses
    intitulés seraient pris pour des titres de chapitres."""
    ep = ecrire_epub(tmp_path, [("p-001", "<p>corps du roman</p>")],
                     toc=[("p-001", "Chapitre premier")])
    texte = epub.extract_epub(ep, tmp_path / "media").text
    assert "Navigation" not in texte
    assert texte.count("Chapitre premier") == 1, "une seule fois, comme TITRE"


# --------------------------------------------------------------------------- #
# Images
# --------------------------------------------------------------------------- #

def test_une_illustration_en_svg_est_extraite(tmp_path):
    """C'est le défaut qui disqualifie Pandoc : en mise en page fixe, les pleines pages sont
    des `<svg><image xlink:href>`, et Pandoc n'émet pas de lien d'image pour elles."""
    corps = ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 2048 1453">'
             '<image width="2048" height="1453" xlink:href="../image/kuchie.jpg"/></svg>')
    ep = ecrire_epub(tmp_path, [("p-001", corps)], images={"image/kuchie.jpg": JPEG})
    ex = epub.extract_epub(ep, tmp_path / "media")
    assert ex.images == ["media/livre_kuchie.jpg"]
    assert "<!-- IMG: media/livre_kuchie.jpg -->" in ex.text
    assert (tmp_path / "media/livre_kuchie.jpg").read_bytes() == JPEG
    assert "<svg" not in ex.text and "xlink" not in ex.text


def test_une_image_img_classique_est_extraite(tmp_path):
    corps = '<p>' + _kobo('avant') + '<img class="fit" src="../image/i-270.jpg" alt=""/></p>'
    ep = ecrire_epub(tmp_path, [("p-001", corps)], images={"image/i-270.jpg": JPEG})
    ex = epub.extract_epub(ep, tmp_path / "media")
    assert ex.images == ["media/livre_i-270.jpg"]
    assert ex.text.splitlines() == ["avant", "", "<!-- IMG: media/livre_i-270.jpg -->"]


def test_une_image_reutilisee_nest_ecrite_quune_fois(tmp_path):
    """La couverture est référencée par la page de couverture ET par la quatrième : deux
    marqueurs, un seul fichier, une seule entrée dans la liste."""
    corps = '<p><img src="../image/cover.jpg"/></p>'
    ep = ecrire_epub(tmp_path, [("p-001", corps), ("p-002", corps)],
                     images={"image/cover.jpg": JPEG})
    ex = epub.extract_epub(ep, tmp_path / "media")
    assert ex.images == ["media/livre_cover.jpg"]
    assert ex.text.count("<!-- IMG: media/livre_cover.jpg -->") == 2


def test_sans_extraction_dimages_rien_nest_ecrit_ni_marque(tmp_path):
    """Même contrat que les .docx : une langue de RÉFÉRENCE (pas la source des images) ne doit
    rien écrire dans media/, sinon les fichiers de deux langues se marchent dessus."""
    corps = '<p>' + _kobo('texte') + '<img src="../image/i-1.jpg"/></p>'
    ep = ecrire_epub(tmp_path, [("p-001", corps)], images={"image/i-1.jpg": JPEG})
    ex = epub.extract_epub(ep, tmp_path / "media", extract_images=False)
    assert ex.images == []
    assert "<!-- IMG:" not in ex.text
    assert not (tmp_path / "media").exists()


def test_une_image_absente_de_l_archive_est_ignoree_sans_planter(tmp_path):
    corps = '<p>' + _kobo('texte') + '<img src="../image/fantome.jpg"/></p>'
    ex = epub.extract_epub(ecrire_epub(tmp_path, [("p-001", corps)]), tmp_path / "media")
    assert ex.images == []
    assert ex.text == "texte"


# --------------------------------------------------------------------------- #
# Titres et découpage
# --------------------------------------------------------------------------- #

def test_une_vraie_balise_de_titre_est_respectee(tmp_path):
    corps = "<h1>Chapitre premier</h1><p>" + _kobo("corps") + "</p>"
    texte = epub.extract_epub(ecrire_epub(tmp_path, [("p-001", corps)]),
                              tmp_path / "media").text
    assert texte.splitlines() == ["# Chapitre premier", "", "corps"]


def test_le_niveau_du_titre_est_conserve(tmp_path):
    """Le pipeline découpe sur DEUX niveaux (Chapitre → Partie) : `<h1>` et `<h2>` ne doivent
    pas être aplatis sur le même."""
    corps = "<h1>Chapitre</h1><p>a</p><h2>Partie</h2><p>b</p>"
    texte = epub.extract_epub(ecrire_epub(tmp_path, [("p-001", corps)]),
                              tmp_path / "media").text
    assert texte.splitlines() == ["# Chapitre", "", "a", "", "## Partie", "", "b"]


@pytest.mark.parametrize("nav_epub3", [True, False], ids=["nav-epub3", "ncx-epub2"])
def test_lintitule_de_la_table_des_matieres_titre_le_document(tmp_path, nav_epub3):
    """Les deux formats de table des matières doivent marcher : le `nav` d'EPUB 3 et le
    `toc.ncx` d'EPUB 2."""
    ep = ecrire_epub(tmp_path, [("p-020", "<p>" + _kobo("le texte du bonus") + "</p>")],
                     toc=[("p-020", "Nouvelle inédite")], nav_epub3=nav_epub3)
    texte = epub.extract_epub(ep, tmp_path / "media").text
    assert texte.splitlines() == ["# Nouvelle inédite", "le texte du bonus"]


def test_une_premiere_ligne_courte_devient_le_titre(tmp_path):
    """Le cas de ce livre : les chapitres s'ouvrent sur un « 一 » posé dans un paragraphe
    STYLÉ (`<p class="font-1em30 bold">`), pas dans une balise de titre — et la feuille de
    style de l'EPUB ne définit même pas cette classe."""
    corps = ('<div class="start-2em"><p class="font-1em30 bold">' + _kobo("一") + "</p></div>"
             "<p>" + _kobo("　特務機関の術師の一日は、昼すぎに始まる。" * 3, 2) + "</p>")
    texte = epub.extract_epub(ecrire_epub(tmp_path, [("p-004", corps)]),
                              tmp_path / "media").text
    assert texte.startswith("# 一\n")


def test_un_titre_doit_etre_court_RELATIVEMENT_a_son_corps(tmp_path):
    """L'épigraphe qui ouvre ce tome — un waka de 45 signes suivi de son attribution de 13 —
    devenait un « chapitre » de 13 caractères : donc une unité de traitement, un appel LLM et
    un titre parasite dans le rendu. La borne absolue ne l'attrape pas ; le rapport, oui."""
    corps = ("<p>" + _kobo("九重に久しく匂へ八重桜　のどけき春の風と知らずや") + "</p>"
             "<p>" + _kobo("──金葉和歌集　中納言実行", 2) + "</p>")
    texte = epub.extract_epub(ecrire_epub(tmp_path, [("p-001", corps)]),
                              tmp_path / "media").text
    assert not texte.startswith("#")


def test_un_document_dune_seule_ligne_nest_pas_un_titre(tmp_path):
    corps = "<p>" + _kobo("une seule réplique isolée") + "</p>"
    texte = epub.extract_epub(ecrire_epub(tmp_path, [("p-001", corps)]),
                              tmp_path / "media").text
    assert texte == "une seule réplique isolée"


def test_une_premiere_ligne_trop_longue_nest_pas_un_titre(tmp_path):
    long = "x" * 60
    corps = f"<p>{long}</p><p>{'y' * 400}</p>"
    texte = epub.extract_epub(ecrire_epub(tmp_path, [("p-001", corps)]),
                              tmp_path / "media").text
    assert not texte.startswith("#")


def test_un_document_sans_titre_prolonge_le_chapitre_precedent(tmp_path):
    """Sinon chaque page d'illustration et chaque épigraphe ouvrirait un « chapitre »."""
    ep = ecrire_epub(tmp_path, [
        ("p-001", "<h1>Chapitre un</h1><p>" + _kobo("corps du chapitre") + "</p>"),
        ("p-002", "<p>" + _kobo("une réplique isolée", 2) + "</p>"),
    ])
    texte = epub.extract_epub(ep, tmp_path / "media").text
    chapitres = split.detect_chapters(texte, None)
    assert len(chapitres) == 1
    assert "une réplique isolée" in chapitres[0].body


def test_les_documents_suivent_lordre_du_SPINE_pas_celui_du_zip(tmp_path):
    """Le zip n'a aucun ordre garanti — sur l'EPUB réel il commence par `p-allcover-001`, puis
    `p-021`, puis `p-colophon`. Seul le spine donne l'ordre de lecture.

    Le zip est donc écrit dans un ordre et le spine déclaré dans un autre : un lecteur qui
    suivrait le zip, l'ordre alphabétique ou le manifeste échouerait ici."""
    ep = ecrire_epub(tmp_path,
                     [("p-009", "<p>troisieme</p>"), ("p-002", "<p>premier</p>"),
                      ("p-005", "<p>deuxieme</p>")],
                     ordre_spine=["p-002", "p-005", "p-009"])
    with zipfile.ZipFile(ep) as z:
        noms = [n for n in z.namelist() if n.endswith(".xhtml")]
    assert noms == ["item/xhtml/p-009.xhtml", "item/xhtml/p-002.xhtml", "item/xhtml/p-005.xhtml"]
    lignes = [ln for ln in epub.extract_epub(ep, tmp_path / "media").text.splitlines() if ln]
    assert lignes == ["premier", "deuxieme", "troisieme"]


# --------------------------------------------------------------------------- #
# Conteneur : robustesse
# --------------------------------------------------------------------------- #

def test_lopf_est_LU_dans_le_conteneur_jamais_devine(tmp_path):
    """Son emplacement varie selon le producteur : `content.opf`, `OEBPS/content.opf`, et
    `item/standard.opf` pour l'EPUB réel de ce dépôt."""
    for base in ("", "OEBPS", "item", "a/b"):
        ep = ecrire_epub(tmp_path, [("p-001", "<p>texte</p>")], base=base,
                         nom=f"l{base.replace('/', '_')}.epub")
        assert epub.extract_epub(ep, tmp_path / "media").text == "texte"


def test_un_conteneur_absent_donne_une_erreur_explicite(tmp_path):
    chemin = tmp_path / "casse.epub"
    with zipfile.ZipFile(chemin, "w") as z:
        z.writestr("mimetype", "application/epub+zip")
    with pytest.raises(RuntimeError, match="container.xml"):
        epub.extract_epub(chemin, tmp_path / "media")


def test_un_document_du_spine_absent_de_larchive_est_saute(tmp_path):
    ep = ecrire_epub(tmp_path, [("p-001", "<p>present</p>")])
    with zipfile.ZipFile(ep, "a") as z:
        opf = z.read("item/standard.opf").decode("utf-8")
    contenu = {}
    with zipfile.ZipFile(ep) as z:
        for n in z.namelist():
            contenu[n] = z.read(n)
    contenu["item/standard.opf"] = opf.replace(
        "<manifest>",
        '<manifest><item id="fantome" href="xhtml/fantome.xhtml" '
        'media-type="application/xhtml+xml"/>').replace(
        "<spine", '<spine').replace('<itemref idref="p-001"/>',
                                    '<itemref idref="fantome"/><itemref idref="p-001"/>').encode(
        "utf-8").decode("utf-8").encode("utf-8")
    ep2 = tmp_path / "recompose.epub"
    with zipfile.ZipFile(ep2, "w") as z:
        for n, d in contenu.items():
            z.writestr(n, d)
    assert epub.extract_epub(ep2, tmp_path / "media").text == "present"


# --------------------------------------------------------------------------- #
# Intégration dans le pipeline
# --------------------------------------------------------------------------- #

def test_extract_dispatche_sur_lextension_epub(tmp_path):
    ep = ecrire_epub(tmp_path, [("p-001", "<p>" + _kobo("par extract()") + "</p>")])
    assert extract.extract(ep, tmp_path / "media").text == "par extract()"


def test_un_format_inconnu_mentionne_epub_dans_son_message(tmp_path):
    faux = tmp_path / "source.rtf"
    faux.write_text("x", encoding="utf-8")
    with pytest.raises(RuntimeError, match="epub"):
        extract.extract(faux, tmp_path / "media")


def test_scan_volume_accepte_un_epub_comme_source(tmp_path):
    """Le bout en bout : un EPUB déposé dans `JAP/` doit être vu comme une source de langue."""
    import yaml

    racine = Path(__file__).resolve().parents[1]
    config = yaml.safe_load((racine / "config.yaml").read_text(encoding="utf-8"))
    vol = tmp_path / "sources" / "MonLN" / "Vol.1" / "JAP"
    vol.mkdir(parents=True)
    ecrire_epub(vol, [
        ("p-001", "<h1>Chapitre un</h1><p>" + _kobo("　" + "本文" * 60) + "</p>"),
        ("p-002", "<h1>Chapitre deux</h1><p>" + _kobo("　" + "続き" * 60, 2) + "</p>"),
    ], nom="Mon LN.epub")
    from pipeline import sources
    plan = sources.scan_volume(vol.parent, config, tmp_path / "build")
    assert list(plan.langs) == ["jp"]
    assert plan.pivot == "jp"
    assert plan.n_chapters == 2
    assert [c.title for c in plan.langs["jp"].chapters] == ["Chapitre un", "Chapitre deux"]


# --------------------------------------------------------------------------- #
# L'EPUB réel (sauté si les sources ne sont pas là — elles ne sont pas versionnées)
# --------------------------------------------------------------------------- #

def test_un_ruby_par_CARACTERE_enregistre_le_COMPOSE(tmp_path):
    """L'autre forme, la plus fréquente sur ce livre (2 668 balises contre 5 472) : chaque
    `<rt>` glose UN idéogramme. Les paires isolées (`堕`→`だ`) n'apprennent rien sur un nom
    propre — c'est le composé qui porte le sens."""
    corps = "<p><ruby>堕<rt>だ</rt>竜<rt>りゆう</rt>講<rt>こう</rt></ruby>の一味</p>"
    ex = epub.extract_epub(ecrire_epub(tmp_path, [("p-001", corps)]), tmp_path / "media")
    assert ex.lectures == {"堕竜講": "だりゆうこう"}
    assert "堕竜講の一味" in ex.text          # le texte rendu, lui, ne change pas


def test_les_deux_formes_de_ruby_cohabitent(tmp_path):
    corps = ("<p><ruby>祭<rt>まつ</rt>花<rt>りか</rt></ruby>と"
             "<ruby>七堕<rt>ナナエ</rt></ruby></p>")
    ex = epub.extract_epub(ecrire_epub(tmp_path, [("p-001", corps)]), tmp_path / "media")
    assert ex.lectures == {"祭花": "まつりか", "七堕": "ナナエ"}


def test_une_glose_de_kanji_isole_reste_enregistree(tmp_path):
    """Un `<ruby>` à UN seul `<rt>` sur UN caractère est un composé d'un caractère : rien
    à recoller, on l'enregistre tel quel."""
    ex = epub.extract_epub(
        ecrire_epub(tmp_path, [("p-001", "<p><ruby>刻<rt>トキ</rt></ruby></p>")]),
        tmp_path / "media")
    assert ex.lectures == {"刻": "トキ"}


@pytest.mark.skipif(not REEL.exists(), reason="sources/roman A absent (non versionné)")
def test_lepub_reel_donne_le_texte_les_images_et_les_chapitres(tmp_path):
    ex = epub.extract_epub(REEL, tmp_path / "media")
    # Pandoc produisait 2 578 904 caractères pour ce livre, dont ~24 000 spans d'habillage.
    assert 150_000 < len(ex.text) < 220_000
    assert len(ex.images) == 23, "16 illustrations en SVG + 7 en <img>"
    assert "koboSpan" not in ex.text and "<svg" not in ex.text
    # Segmentation intacte : ces termes ne doivent pas être coupés par une espace.
    for terme in ("千万丈塔", "八重山吹", "七堕", "特務機関"):
        assert terme in ex.text
    assert "七堕ナナエ" not in ex.text, "furigana collé au kanji"

    titres = [c.title for c in split.detect_chapters(ex.text, None)]
    for attendu in ("序", "一", "二", "三", "四", "終"):
        assert attendu in titres, attendu


# --------------------------------------------------------------------------- #
# Lexique des lectures : collecté SANS toucher au texte rendu
# --------------------------------------------------------------------------- #

def test_les_lectures_sont_collectees_meme_en_mode_ignorer(tmp_path):
    """Le seul agent qui a besoin des furigana est le TERMINOLOGUE, et seulement pour
    romaniser quelques noms propres. Les inliner gonfle la source de 30 % et noie le
    traducteur : on collecte donc TOUJOURS, dans un canal séparé, sans nouveau mode."""
    ex = epub.extract_epub(ecrire_epub(tmp_path, [("p-001", RUBY)]), tmp_path / "media")
    assert ex.lectures == {"七堕": "ナナエ"}
    assert "ナナエ" not in ex.text          # le texte, lui, reste propre


def test_un_ruby_par_MOT_apparie_chaque_base_a_SA_lecture(tmp_path):
    """Ruby par MOT : chaque `<rt>` glose un mot entier. Accumuler toutes les bases d'un
    côté et toutes les lectures de l'autre produirait la paire fausse « 千万丈塔踏破儀式 »."""
    corps = ("<p><ruby>千万丈塔<rt>せんまんじようとう</rt>踏破儀式<rt>とうはぎしき</rt>"
             "</ruby>を開始する</p>")
    ex = epub.extract_epub(ecrire_epub(tmp_path, [("p-001", corps)]), tmp_path / "media")
    assert ex.lectures == {"千万丈塔": "せんまんじようとう", "踏破儀式": "とうはぎしき"}


def test_les_lectures_ignorent_rp_et_acceptent_rb(tmp_path):
    corps = ("<p><ruby>七堕<rp>（</rp><rt>ナナエ</rt><rp>）</rp></ruby>"
             "<ruby><rb>八重山吹</rb><rt>ヤエヤマブキ</rt></ruby></p>")
    ex = epub.extract_epub(ecrire_epub(tmp_path, [("p-001", corps)]), tmp_path / "media")
    assert ex.lectures == {"七堕": "ナナエ", "八重山吹": "ヤエヤマブキ"}


def test_les_gloses_qui_ne_sont_pas_des_mots_sont_ecartees(tmp_path):
    """Une lecture sert à romaniser un NOM : on écarte le ruby posé sur une phrase entière
    (ça existe) et celui posé sur du latin, qui n'apprend rien."""
    corps = ("<p><ruby>これは非常に長い文章であって語ではない<rt>よみ</rt></ruby>"
             "<ruby>Semifer<rt>セミフェル</rt></ruby>"
             "<ruby>七堕<rt>ナナエ</rt></ruby></p>")
    ex = epub.extract_epub(ecrire_epub(tmp_path, [("p-001", corps)]), tmp_path / "media")
    assert ex.lectures == {"七堕": "ナナエ"}


def test_les_lectures_sont_fusionnees_sur_tout_le_spine(tmp_path):
    """Les EPUB japonais ne glosent en général que la PREMIÈRE occurrence : une lecture vue
    au chapitre 1 doit rester disponible au chapitre 4."""
    ex = epub.extract_epub(
        ecrire_epub(tmp_path, [("p-001", "<p><ruby>七堕<rt>ナナエ</rt></ruby>だ</p>"),
                               ("p-002", "<p><ruby>祭花<rt>まつりか</rt></ruby>だ</p>")]),
        tmp_path / "media")
    assert ex.lectures == {"七堕": "ナナエ", "祭花": "まつりか"}


def test_un_format_sans_furigana_rend_un_lexique_vide(tmp_path):
    """`Extracted.lectures` existe pour tous les formats : seul l'EPUB le remplit."""
    f = tmp_path / "v.txt"
    f.write_text("Du texte sans le moindre ruby.", encoding="utf-8")
    assert extract.extract(f, tmp_path / "media").lectures == {}


def test_lecture_dominante_prefere_la_plus_frequente():
    """Un même kanji est souvent glosé de plusieurs façons — 434 graphies sur 2 029 dans le
    livre réel, presque toujours une lecture canonique plus des *gikun* isolés (lectures
    sémantiques d'auteur). Retenir la première rencontrée choisirait parfois le cas isolé."""
    from collections import Counter
    comptes = {"天茜": Counter({"きようだい": 1, "あかね": 458}),
               "碧燈": Counter({"あおひ": 346})}
    assert epub.lecture_dominante(comptes) == {"天茜": "あかね", "碧燈": "あおひ"}


def test_lecture_dominante_est_deterministe_a_egalite():
    """`Counter.most_common` départage par ordre d'insertion : à égalité, c'est la première
    rencontrée dans l'ordre du spine qui gagne — arbitraire, mais reproductible."""
    from collections import Counter
    c = Counter()
    c["エナガ一三七"] += 1
    c["まつりか"] += 1
    assert epub.lecture_dominante({"祭花": c}) == {"祭花": "エナガ一三七"}


def test_un_ruby_par_CARACTERE_enregistre_le_COMPOSE(tmp_path):
    """L'autre forme, la plus fréquente sur ce livre (2 668 balises contre 5 472) : chaque
    `<rt>` glose UN idéogramme. Les paires isolées (`堕`→`だ`) n'apprennent rien sur un nom
    propre — c'est le composé qui porte le sens."""
    corps = "<p><ruby>堕<rt>だ</rt>竜<rt>りゆう</rt>講<rt>こう</rt></ruby>の一味</p>"
    ex = epub.extract_epub(ecrire_epub(tmp_path, [("p-001", corps)]), tmp_path / "media")
    assert ex.lectures == {"堕竜講": "だりゆうこう"}
    assert "堕竜講の一味" in ex.text          # le texte rendu, lui, ne change pas


def test_les_deux_formes_de_ruby_cohabitent(tmp_path):
    corps = ("<p><ruby>祭<rt>まつ</rt>花<rt>りか</rt></ruby>と"
             "<ruby>七堕<rt>ナナエ</rt></ruby></p>")
    ex = epub.extract_epub(ecrire_epub(tmp_path, [("p-001", corps)]), tmp_path / "media")
    assert ex.lectures == {"祭花": "まつりか", "七堕": "ナナエ"}


def test_une_glose_de_kanji_isole_reste_enregistree(tmp_path):
    """Un `<ruby>` à UN seul `<rt>` sur UN caractère est un composé d'un caractère : rien
    à recoller, on l'enregistre tel quel."""
    ex = epub.extract_epub(
        ecrire_epub(tmp_path, [("p-001", "<p><ruby>刻<rt>トキ</rt></ruby></p>")]),
        tmp_path / "media")
    assert ex.lectures == {"刻": "トキ"}


@pytest.mark.skipif(not REEL.exists(), reason="EPUB réel absent (sources non versionnées)")
def test_les_lectures_du_livre_reel(tmp_path):
    ex = epub.extract_epub(REEL, tmp_path / "media")
    assert len(ex.lectures) > 1500
    # Les noms restés en japonais dans le rendu du Vol.1 — c'est exactement l'information
    # qui manquait au terminologue pour proposer « Akane » plutôt que de recopier 天茜.
    # Chacun a ici une lecture NETTEMENT majoritaire (458, 346, 295, 14 occurrences).
    for base, lecture in [("天茜", "あかね"), ("碧燈", "あおひ"),
                          ("七堕", "ナナエ"), ("八重山吹", "ヤエヤマブキ")]:
        assert ex.lectures.get(base) == lecture, base
    # RÉGRESSION CORRIGÉE : 祭花 n'apparaît en entier qu'avec son indicatif radio
    # (エナガ一三七, 1 occurrence). Sa vraie lecture まつりか est écrite en ruby PAR
    # CARACTÈRE, 388 fois — invisible tant que le composé n'était pas recollé. Le
    # glossaire en avait tiré une héroïne nommée « Enaga ».
    for base, lecture in [("祭花", "まつりか"), ("凜雪", "りんぜつ"),
                          ("堕竜講", "だりゆうこう"), ("真神", "まがみ")]:
        assert ex.lectures.get(base) == lecture, base


# --------------------------------------------------------------------------- #
# Paragraphes — ce qui rend la source DÉCOUPABLE
# --------------------------------------------------------------------------- #
#
# `split._paragraphs` ne sépare que sur les lignes VIDES, et `split.split_proportional` ne
# sait aligner une source de référence sur les blocs du pivot qu'aux frontières de
# paragraphes. Tant que les blocs et les `<br/>` produisaient tous deux un saut simple, un
# document XHTML entier ressortait en UN SEUL paragraphe insécable.
#
# Mesuré sur roman B Vol.3 (japonais) : 20 paragraphes pour 112 107 caractères, dont un de
# 40 177. En alignant cette référence sur les 54 blocs du pivot anglais, 43 morceaux
# ressortaient VIDES — 43 blocs partaient donc au traducteur sans une ligne de japonais,
# pendant que 11 en recevaient des masses sans rapport avec eux.

def test_deux_paragraphes_sont_separes_par_une_ligne_vide(tmp_path):
    # ⚠ Textes assez longs pour que `titrer` ne promeuve pas la 1re ligne en intitulé : ce
    # test porte sur la frontière de paragraphe, pas sur le titrage.
    corps = "<p>" + _kobo("ligne un") + "</p><p>" + _kobo("ligne deux", 2) + "</p>"
    texte = epub.extract_epub(ecrire_epub(tmp_path, [("p-001", corps)]),
                              tmp_path / "media").text
    assert texte == "ligne un\n\nligne deux"


def test_un_document_donne_autant_de_paragraphes_que_de_blocs(tmp_path):
    """**Le test central.** Il relie le module à la fonction qui en dépend : c'est sa
    violation qui produisait 20 paragraphes pour 112 107 caractères."""
    corps = "".join(f"<p>{_kobo(f'le bloc numero {i}', i)}</p>" for i in range(1, 13))
    texte = epub.extract_epub(ecrire_epub(tmp_path, [("p-001", corps)]),
                              tmp_path / "media").text
    assert len(split._paragraphs(texte)) == 12


def test_un_br_ne_cree_pas_de_paragraphe(tmp_path):
    """Le pendant négatif : un vers, une réplique coupée, une adresse restent UN paragraphe.
    Les promouvoir en frontières hacherait la source au lieu de la rendre découpable."""
    corps = "<p>" + _kobo("avant") + "<br/>" + _kobo("apres", 2) + "</p>"
    texte = epub.extract_epub(ecrire_epub(tmp_path, [("p-001", corps)]),
                              tmp_path / "media").text
    assert texte == "avant\napres"
    assert len(split._paragraphs(texte)) == 1


def test_des_blocs_imbriques_ne_font_pas_de_lignes_vides_en_rafale(tmp_path):
    """`<div><p>…</p></div>` clôt la ligne deux fois. Une succession de lignes blanches ne
    dit rien de plus qu'une seule, et gonflerait la source transmise au modèle."""
    corps = ("<div><p>" + _kobo("ligne un") + "</p></div>"
             "<div><p>" + _kobo("ligne deux", 2) + "</p></div>")
    texte = epub.extract_epub(ecrire_epub(tmp_path, [("p-001", corps)]),
                              tmp_path / "media").text
    assert texte == "ligne un\n\nligne deux"
    assert "\n\n\n" not in texte


def test_un_titre_reste_un_paragraphe_a_lui_seul(tmp_path):
    """`split._paragraphs` isole déjà les lignes `#`. La frontière ne doit pas les coller au
    corps, sinon un titre de Partie serait fondu dans la prose au découpage en blocs."""
    corps = "<h1>Titre</h1><p>" + _kobo("corps") + "</p>"
    texte = epub.extract_epub(ecrire_epub(tmp_path, [("p-001", corps)]),
                              tmp_path / "media").text
    assert split._paragraphs(texte) == ["# Titre", "corps"]


def test_les_elements_inline_ne_sont_toujours_pas_separes(tmp_path):
    """⚠ Non-régression du piège central du module : le correctif ne touche QU'AUX éléments
    déjà traités comme blocs. Un `<span>` ou un `<ruby>` qui ouvrirait un paragraphe
    disloquerait le japonais, qui n'a pas d'espace entre les mots."""
    corps = "<p><span>千万</span><span>丈塔</span>と<a href='#x'>呼ぶ</a></p>"
    texte = epub.extract_epub(ecrire_epub(tmp_path, [("p-001", corps)]),
                              tmp_path / "media").text
    assert texte == "千万丈塔と呼ぶ"
    assert len(split._paragraphs(texte)) == 1


def test_un_document_dun_seul_paragraphe_nest_toujours_pas_titre(tmp_path):
    """⚠ Le piège de `titrer` : il compte les lignes du document pour décider qu'une première
    ligne courte est un intitulé. Si les frontières de paragraphe étaient comptées, un
    document d'UN paragraphe passerait pour un document de deux lignes — et chaque page
    d'illustration ou d'épigraphe redeviendrait un chapitre."""
    texte = epub.extract_epub(ecrire_epub(tmp_path, [("p-001", "<p>Court</p>")]),
                              tmp_path / "media").text
    assert texte == "Court"                      # pas de « # Court »
