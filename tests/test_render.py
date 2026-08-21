# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Alexandre Tournel

"""Tests de render.py : normalisation des fences Pandoc et retrait du tiret de
dialogue — les deux garde-fous déterministes appliqués avant Pandoc."""
import shutil
from pathlib import Path

import pytest

from pipeline.render import _normalize_fences, _strip_dialogue_dashes


def test_normalize_fences_keeps_legitimate_triple_colon():
    line = '::: {.dialogue custom-style="List Paragraph"}'
    assert _normalize_fences(line) == line


def test_normalize_fences_normalizes_four_colons_to_three():
    line = ':::: {.dialogue custom-style="List Paragraph"}'
    assert _normalize_fences(line) == '::: {.dialogue custom-style="List Paragraph"}'


def test_normalize_fences_keeps_plain_closing():
    assert _normalize_fences(":::") == ":::"


def test_normalize_fences_strips_hallucinated_mid_sentence_colons():
    """Régression : le modèle invente parfois des ::/::: en PLEIN MILIEU d'une phrase
    de narration en essayant d'envelopper une réplique intégrée — ça doit être retiré
    sans abîmer le reste de la phrase."""
    line = "Tiat plissa les yeux. :: Est-elle... la vôtre ? demanda-t-elle maladroitement. :::"
    out = _normalize_fences(line)
    assert "::" not in out
    assert "Tiat plissa les yeux." in out
    assert "Est-elle" in out and "maladroitement" in out


def test_normalize_fences_untouched_normal_line():
    line = "Une phrase de narration tout à fait normale."
    assert _normalize_fences(line) == line


def test_strip_correction_annotations_removes_inline_meta_commentary():
    """Régression réelle (Vol.2 en production) : un agent (le correcteur, p. ex.) narrait
    sa propre correction en plein texte au lieu de la garder pour lui."""
    from pipeline.render import _strip_correction_annotations
    t = 'Le bogard s\'assombrit. (Correction : "bogard" au lieu de "boggard").'
    out = _strip_correction_annotations(t)
    assert "Correction" not in out
    assert "Le bogard s'assombrit." in out


def test_normalize_fences_reconstructs_inline_crammed_dialogue():
    """Régression réelle (Vol.2 en production) : mon propre gabarit montrait le format
    SANS retours à la ligne, et le modèle l'a recopié fidèlement — Pandoc ignore
    silencieusement une fence qui n'est pas sur sa propre ligne, d'où le
    `{.dialogue custom-style="..."}` littéral dans le document final. Doit être
    reconstruit en 3 lignes propres, attributs INCLUS (pas juste les « ::: » retirés
    en laissant les accolades trainer)."""
    line = '::: {.dialogue custom-style="List Paragraph"} « Je l\'ai ! » :::'
    out = _normalize_fences(line)
    assert '::: {.dialogue custom-style="List Paragraph"}' in out
    assert "« Je l'ai ! »" in out
    assert out.count(":::") == 2  # une ouverture, une fermeture — chacune sur sa ligne
    lines = [l for l in out.splitlines() if l.strip()]
    assert lines[0] == '::: {.dialogue custom-style="List Paragraph"}'
    assert lines[-1] == ':::'


def test_normalize_fences_already_multiline_is_idempotent():
    good = '::: {.dialogue custom-style="List Paragraph"}\n« Déjà bon. »\n:::'
    out = _normalize_fences(good)
    assert '{.dialogue custom-style="List Paragraph"}' in out
    assert "« Déjà bon. »" in out


def test_sanitize_custom_styles_unwraps_unknown_style_name():
    """Régression réelle (roman B Vol.3) : l'agent mise en page a nommé un bloc
    `custom-style="Corps de texte"` — le nom AFFICHÉ dans Word, alors que le style réel
    s'appelle « Body Text » en interne (reference.docx). Pandoc, ne le retrouvant pas
    par nom, crée un styleId EN DOUBLE avec le vrai « Corps de texte », ce qui corrompt
    le style de narration pour tout le document. Le bloc doit être déballé en texte
    simple plutôt que transmis tel quel à Pandoc."""
    from pipeline.render import _sanitize_custom_styles
    md = ('::: {.dialogue custom-style="Corps de texte"}\n'
          'Un texte qui ne devrait pas être un dialogue.\n:::')
    out = _sanitize_custom_styles(md, {"List Paragraph", "Pensée"})
    assert ":::" not in out
    assert "Un texte qui ne devrait pas être un dialogue." in out


def test_sanitize_custom_styles_keeps_known_style():
    from pipeline.render import _sanitize_custom_styles
    md = '::: {.dialogue custom-style="List Paragraph"}\n« Bonjour ! »\n:::'
    out = _sanitize_custom_styles(md, {"List Paragraph", "Pensée"})
    assert out == md


def test_normalize_fences_two_inline_dialogues_with_narration_between():
    """Cas réel observé : deux répliques ET une phrase de narration intercalée, le
    tout sur un seul paragraphe avec un nombre de « : » incohérent (::::/:::::)."""
    line = (':::: {.dialogue custom-style="X"} « A » ::: La fille bondit. '
           '::::: {.dialogue custom-style="X"} « B » :::')
    out = _normalize_fences(line)
    assert out.count('{.dialogue custom-style="X"}') == 2
    assert "« A »" in out and "« B »" in out
    assert "La fille bondit." in out


def test_strip_dialogue_dashes_removes_leading_dash_in_dialogue_block():
    md = (':::{.dialogue custom-style="List Paragraph"}\n'
          '— H-hey !\n'
          ':::')
    out = _strip_dialogue_dashes(md)
    assert "— H-hey" not in out
    assert "H-hey !" in out


def test_strip_dialogue_dashes_untouched_outside_dialogue():
    md = "Narration normale avec un tiret — comme ceci — dans la phrase."
    assert _strip_dialogue_dashes(md) == md


def test_strip_dialogue_dashes_second_block_without_dash_untouched():
    md = (':::{.dialogue custom-style="List Paragraph"}\n'
          'Déjà sans tiret.\n'
          ':::')
    assert "Déjà sans tiret." in _strip_dialogue_dashes(md)


def test_strip_dialogue_quotes_removes_in_dialogue_keeps_in_narration():
    """Les « » encadrant une réplique disparaissent au rendu ; ceux en narration restent."""
    from pipeline.render import _strip_dialogue_quotes
    md = ('::: {.dialogue custom-style="List Paragraph"}\n'
          '« Pas possible ? »\n'
          ':::\n\n'
          'Narration avec une « citation » à garder.\n\n'
          '::: {.dialogue custom-style="List Paragraph"}\n'
          '— « Hé ! »\n'
          ':::')
    out = _strip_dialogue_quotes(md)
    assert "« Pas possible" not in out and "Pas possible ?" in out
    assert "« Hé ! »" not in out and "Hé !" in out
    assert "« citation »" in out          # narration intacte


def test_strip_leaked_glossary_removes_entries_keeps_narration():
    """Régression réelle (Vol.2) : le glossaire a fui dans le texte final. Le filet au
    rendu doit retirer les entrées de glossaire SANS toucher au récit alentour."""
    from pipeline.render import _strip_leaked_glossary
    md = ("Une ville a brûlé.\n\n"
          "## Personnages (le genre commande les accords)\n"
          "Feodor Jessman [masculin, FORCÉ] — Quatrième officier de la 5e division.\n"
          "Lakhesh [féminin] — Jeune fille à traits félins.\n\n"
          "## Objets\n"
          "Arme Enchantée [FORCÉ] — Objet auquel un Esprit est associé.\n\n"
          "Elle entra dans la pièce — lentement — et sourit.")
    out = _strip_leaked_glossary(md)
    assert "FORCÉ]" not in out
    assert "## Personnages" not in out and "## Objets" not in out
    assert "Une ville a brûlé." in out
    assert "Elle entra dans la pièce — lentement — et sourit." in out   # récit avec — préservé


def test_strip_leaked_glossary_leaves_normal_bullet_list_alone():
    """Une vraie liste à puces du récit (sans tags de glossaire) ne doit pas être touchée."""
    from pipeline.render import _strip_leaked_glossary
    md = ("Sa liste de courses :\n\n"
          "- du pain — pour le matin\n"
          "- du lait — pour le café\n\n"
          "Elle sortit.")
    assert _strip_leaked_glossary(md) == md


def test_looks_like_glossary_detects_leak_and_ignores_prose():
    from pipeline.orchestrator import _looks_like_glossary
    glo = ("## Personnages\n- Feodor [masculin, FORCÉ] — officier (variantes : Féodor)\n"
           "- Tiat [féminin] — soldate")
    assert _looks_like_glossary(glo) is True
    assert _looks_like_glossary("Il réfléchit aux variantes : la première était risquée.") is False


def test_segment_dialogues_wraps_unwrapped_reply():
    """Régression réelle (Vol.3) : le 9B ne balise que la moitié des répliques ; les
    autres ressortent en texte courant avec « » et sans style. Une réplique « … » doit
    devenir un bloc .dialogue."""
    from pipeline.render import _segment_dialogues
    md = "Narration ici.\n\n« Une réplique nue ? »\n\nSuite de narration."
    out = _segment_dialogues(md, "List Paragraph")
    assert '::: {.dialogue custom-style="List Paragraph"}' in out
    assert "Une réplique nue ?" in out
    assert out.count(".dialogue") == 1


def test_segment_dialogues_splits_mixed_reply_narration_reply():
    """Régression réelle (Vol.3 ch01) : « Écarte-toi ! » narration « Même toi... ! » était
    enveloppé EN ENTIER dans un seul bloc dialogue → le » du milieu survivait et la
    narration était mal catégorisée. Doit être éclaté en dialogue / narration / dialogue."""
    from pipeline.render import _segment_dialogues
    md = ('::: {.dialogue custom-style="List Paragraph"}\n'
          '« Écarte-toi d\'ici, Nasania ! » La fille hurla avec rage. '
          '« Même toi devrais savoir qui est notre ennemi ! »\n:::')
    out = _segment_dialogues(md, "List Paragraph")
    assert out.count('.dialogue custom-style="List Paragraph"}') == 2   # deux répliques
    assert "La fille hurla avec rage." in out                          # narration hors bloc
    # la narration n'est PAS dans un bloc dialogue
    import re
    blocks = re.findall(r':::.*?:::', out, re.DOTALL)
    assert not any("hurla avec rage" in b for b in blocks)


def test_segment_dialogues_keeps_speech_verb_attribution_attached():
    """L'incise d'attribution qui suit une réplique et commence par un verbe de parole
    (« hurla-t-elle… ») reste DANS le bloc dialogue jusqu'à la fin de phrase ; le reste
    repart en narration."""
    from pipeline.render import _segment_dialogues
    md = ('::: {.dialogue custom-style="List Paragraph"}\n'
          '« Tu es sérieuse ?! » hurla-t-elle en chargeant ; leurs épées s\'entrechoquèrent.\n:::')
    out = _segment_dialogues(md, "List Paragraph")
    assert out.count('.dialogue custom-style="List Paragraph"}') == 1
    import re
    block = re.search(r':::.*?:::', out, re.DOTALL).group(0)
    assert "hurla-t-elle en chargeant ;" in block            # incise collée à la réplique
    assert "leurs épées s’entrechoquèrent." in out or "leurs épées s'entrechoquèrent." in out
    # la 2e phrase (narration) n'est PAS dans le bloc dialogue
    assert "s’entrechoquèrent" not in block and "s'entrechoquèrent" not in block


def test_segment_dialogues_non_attribution_narration_stays_separate():
    """Un récit qui suit une réplique mais ne commence PAS par un verbe de parole
    (« La fille… ») reste une narration séparée, pas une incise."""
    from pipeline.render import _segment_dialogues
    md = ('« Écarte-toi ! » La fille brandit son arme avec rage. « Écoute-moi ! »')
    out = _segment_dialogues(md, "List Paragraph")
    assert out.count('.dialogue custom-style="List Paragraph"}') == 2
    import re
    blocks = re.findall(r':::.*?:::', out, re.DOTALL)
    assert not any("brandit son arme" in b for b in blocks)   # narration hors dialogue
    assert "La fille brandit son arme avec rage." in out


def test_segment_dialogues_keeps_embedded_quoted_phrase_in_narration():
    """Régression : une phrase CITÉE au fil de la narration (« … » précédée de « que »,
    « d' », etc. — pas une réplique autonome) ne doit PAS être extraite en bloc dialogue,
    sinon la phrase de narration est fragmentée."""
    from pipeline.render import _segment_dialogues
    md = ("On leur avait appris que « ce cargo transporte des armes vers les lignes "
          "frontales ». Leur mission était donc d'« éviter une tragédie majeure ».")
    out = _segment_dialogues(md, "List Paragraph")
    assert ".dialogue" not in out          # narration intacte, aucune découpe
    assert out.strip() == md


def test_segment_dialogues_keeps_cited_term_in_narration():
    """Un terme CITÉ en narration (« Leprechauns ») n'est PAS une réplique : le paragraphe
    reste de la narration, sans découpe ni bloc dialogue."""
    from pipeline.render import _segment_dialogues
    md = "On raconte la légende des esprits appelés « Leprechauns »."
    out = _segment_dialogues(md, "List Paragraph")
    assert ".dialogue" not in out
    assert out.strip() == md


def test_segment_dialogues_leaves_pure_block_and_markers():
    from pipeline.render import _segment_dialogues
    md = ('# Titre\n\n<!-- IMG: media/x.png -->\n\n'
          '::: {.dialogue custom-style="List Paragraph"}\n« Réplique pure ? »\n:::')
    out = _segment_dialogues(md, "List Paragraph")
    assert "# Titre" in out and "<!-- IMG: media/x.png -->" in out
    assert out.count(".dialogue") == 1                       # bloc pur inchangé


def test_segment_dialogues_attaches_trailing_period_no_orphan():
    """Régression réelle (Vol.3 ch02) : un point HORS des guillemets après une réplique
    (« … ciel… ». puis fin) ne doit pas rester un paragraphe « . » orphelin ; il est
    rattaché à la réplique (ou absorbé)."""
    from pipeline.render import _segment_dialogues
    md = "« Il a déjà quitté ce ciel… »."
    out = _segment_dialogues(md, "List Paragraph").strip()
    import re
    # aucun paragraphe réduit à de la seule ponctuation
    assert not any(re.fullmatch(r'[.\s]+', p.strip()) for p in re.split(r'\n\s*\n', out))
    assert out.count(".dialogue") == 1


def test_segment_dialogues_period_between_two_replies():
    """« A ». « B ». → deux blocs dialogue, aucun point orphelin entre eux."""
    from pipeline.render import _segment_dialogues
    md = "« Pars maintenant ! ». « Reviens vite ! »."
    out = _segment_dialogues(md, "List Paragraph")
    import re
    parts = [p for p in re.split(r'\n\s*\n', out) if p.strip()]
    assert out.count(".dialogue") == 2
    assert not any(re.fullmatch(r'[.\s]+', p.strip()) for p in parts)


def test_strip_leaked_style_guide_removes_title_and_guide_lines():
    """Régression réelle (Vol.3) : le 9B a recopié le titre du guide de style en tête de
    bloc. On le retire, ainsi que toute ligne identique à une ligne du guide."""
    from pipeline.render import _strip_leaked_style_guide
    guide = ["# Guide de style — conventions générales de traduction",
             "## Ponctuation", "Utilise les guillemets français « »."]
    md = ("# Guide de style — conventions générales de traduction\n\n"
          "Utilise les guillemets français « ».\n\n"
          "C'était une histoire ancienne.")
    out = _strip_leaked_style_guide(md, guide)
    assert "Guide de style" not in out
    assert "Utilise les guillemets" not in out
    assert "C'était une histoire ancienne." in out


def test_collapse_repetitions_collapses_looped_cycle():
    """Régression réelle (Vol.3 ch01) : le modèle boucle sur un échange de dialogue.
    Un cycle de paragraphes substantiels répété doit être réduit à une occurrence."""
    from pipeline.render import _collapse_repetitions
    a = "« Le bien n'est qu'une question d'angle, dit-elle avec une colère froide et contenue. »"
    b = "« Comment oses-tu dire une chose pareille, alors que tu connais la vérité ?! »"
    md = "\n\n".join([a, b] * 5 + ["La bataille se poursuivit sans répit dans la nuit."])
    out = _collapse_repetitions(md)
    assert out.count(a) == 1 and out.count(b) == 1
    assert "La bataille se poursuivit" in out


def test_collapse_repetitions_keeps_short_legit_repeats():
    """Les répétitions COURTES légitimes (SFX « *Clang.* ») ne sont pas effondrées."""
    from pipeline.render import _collapse_repetitions
    md = "*Clang.*\n\n*Clang.*\n\n*Clang.*"
    assert _collapse_repetitions(md).count("*Clang.*") == 3


# --------------------------------------------------------------------------- #
# Marqueurs d'image et filtre anti-boucle. Régression réelle (roman B Vol.2) :
# le séparateur de scène, répété 31 fois dans le tome, était pris pour une boucle
# du modèle et effondré à UNE occurrence — 28 marqueurs dans le Markdown, 5 après
# ce filtre. Le marqueur porte ses dimensions Pandoc, ce qui lui faisait franchir
# le seuil des 80 caractères par la seule précision des flottants.
# --------------------------------------------------------------------------- #

_SEP = ('<!-- IMG: media/image15.png|{width="0.11624890638670166in" '
        'height="0.22125in"} -->')


def test_collapse_repetitions_keeps_every_repeated_image_marker():
    from pipeline.render import _collapse_repetitions
    assert len(_SEP) > 80, "le marqueur doit dépasser le seuil, sinon le test ne prouve rien"
    paras = []
    for i in range(25):
        paras += [f"Scène numéro {i} du chapitre, racontée en quelques mots.", _SEP]
    out = _collapse_repetitions("\n\n".join(paras))
    assert out.count(_SEP) == 25


def test_collapse_repetitions_keeps_consecutive_image_markers():
    """Deux séparateurs de suite (cycle d'images pur) : rien à effondrer non plus."""
    from pipeline.render import _collapse_repetitions
    md = "\n\n".join([_SEP] * 6)
    assert _collapse_repetitions(md).count(_SEP) == 6


def test_collapse_repetitions_still_collapses_a_loop_containing_an_image():
    """Un vrai cycle de PROSE reste effondré même s'il contient un marqueur d'image :
    l'exemption porte sur le paragraphe-marqueur, pas sur le cycle qui l'entoure."""
    from pipeline.render import _collapse_repetitions
    a = "« Le bien n'est qu'une question d'angle, dit-elle avec une colère froide et contenue. »"
    md = "\n\n".join([a, _SEP] * 5 + ["La bataille se poursuivit sans répit."])
    out = _collapse_repetitions(md)
    assert out.count(a) == 1
    assert "La bataille se poursuivit" in out


def test_render_reports_image_markers_lost_by_filters(tmp_path, monkeypatch):
    """`render()` doit signaler toute image supprimée par la chaîne de filtres et remplir
    `stats` — c'est l'absence de ce contrôle qui a rendu la perte invisible."""
    import pipeline.render as R
    md = tmp_path / "t.md"
    md.write_text("\n\n".join(["Texte.", _SEP, "Suite.", _SEP]), encoding="utf-8")
    # filtre saboteur : simule un nettoyage qui mange un marqueur
    monkeypatch.setattr(R, "_collapse_repetitions",
                        lambda t: t.replace(_SEP, "", 1))
    monkeypatch.setattr(R.shutil, "which", lambda p: "pandoc")
    monkeypatch.setattr(R, "_run", lambda cmd, cwd: None)
    cfg = {"rendu": {"metadata": {"titre": "T", "auteur": "A", "langue": "fr"},
                     "formats": [], "styles": {}},
           "chemins": {}}
    msgs: list[str] = []
    st: dict = {}
    R.render(md, tmp_path, cfg, warn=msgs.append, stats=st)
    assert st == {"images_markdown": 2, "images_rendu": 1}
    assert msgs and "marqueur(s) d'image supprimé(s)" in msgs[0]


def test_render_stays_silent_when_no_image_is_lost(tmp_path, monkeypatch):
    import pipeline.render as R
    md = tmp_path / "t.md"
    md.write_text("\n\n".join(["Texte.", _SEP, "Suite.", _SEP]), encoding="utf-8")
    monkeypatch.setattr(R.shutil, "which", lambda p: "pandoc")
    monkeypatch.setattr(R, "_run", lambda cmd, cwd: None)
    cfg = {"rendu": {"metadata": {"titre": "T", "auteur": "A", "langue": "fr"},
                     "formats": [], "styles": {}},
           "chemins": {}}
    msgs: list[str] = []
    st: dict = {}
    R.render(md, tmp_path, cfg, warn=msgs.append, stats=st)
    assert st == {"images_markdown": 2, "images_rendu": 2}
    assert msgs == []


def test_render_works_without_warn_or_stats(tmp_path, monkeypatch):
    """Rétro-compatibilité : les appelants existants (`--render-only`) n'ont pas changé."""
    import pipeline.render as R
    md = tmp_path / "t.md"
    md.write_text(f"Texte.\n\n{_SEP}", encoding="utf-8")
    monkeypatch.setattr(R.shutil, "which", lambda p: "pandoc")
    monkeypatch.setattr(R, "_run", lambda cmd, cwd: None)
    cfg = {"rendu": {"metadata": {"titre": "T", "auteur": "A", "langue": "fr"},
                     "formats": [], "styles": {}},
           "chemins": {}}
    assert R.render(md, tmp_path, cfg) == []


def test_render_md_carries_version_metadata_block(tmp_path, monkeypatch):
    """Le .render.md passé à Pandoc doit porter la version en bloc YAML de TÊTE, avec
    `keywords` ET `subject` en LISTE. Les deux détails sont load-bearing (cf. le test
    d'intégration ci-dessous) : une chaîne au lieu d'une liste, ou `keywords` seul, et
    l'empreinte disparaît silencieusement du fichier livré."""
    import pipeline.render as R
    from core.version import __version__

    md = tmp_path / "t.md"
    md.write_text("Texte.", encoding="utf-8")
    vu: dict = {}
    monkeypatch.setattr(R.shutil, "which", lambda p: "pandoc")
    # `_run` est le seul moment où le .render.md existe : il est supprimé en `finally`.
    monkeypatch.setattr(R, "_run",
                        lambda cmd, cwd: vu.setdefault(
                            "md", (tmp_path / "t.render.md").read_text(encoding="utf-8")))
    cfg = {"rendu": {"metadata": {"titre": "T", "auteur": "A", "langue": "fr"},
                     "formats": ["docx"], "styles": {},
                     "reference_docx": "templates/reference.docx"},
           "chemins": {}}
    monkeypatch.setattr(R, "_normalize_docx", lambda *a, **k: None)
    monkeypatch.setattr(R, "_narration_style_id", lambda p: "Corpsdetexte")
    R.render(md, tmp_path, cfg)

    contenu = vu["md"]
    assert contenu.startswith("---\n"), "le bloc YAML doit être en TÊTE (exigence Pandoc)"
    assert f"keywords:\n  - Angelith {__version__}" in contenu
    assert f"subject:\n  - Angelith {__version__}" in contenu
    assert "Texte." in contenu


def test_render_passes_no_keywords_via_metadata_flag(tmp_path, monkeypatch):
    """Garde-fou explicite : ne PAS revenir à `--metadata keywords=…`. Pandoc 3.10
    l'ignore en silence côté docx (il attend une liste), ce qui laissait cp:keywords
    vide sans le moindre message."""
    import pipeline.render as R
    md = tmp_path / "t.md"
    md.write_text("Texte.", encoding="utf-8")
    cmds: list[list[str]] = []
    monkeypatch.setattr(R.shutil, "which", lambda p: "pandoc")
    monkeypatch.setattr(R, "_run", lambda cmd, cwd: cmds.append(cmd))
    monkeypatch.setattr(R, "_normalize_docx", lambda *a, **k: None)
    monkeypatch.setattr(R, "_narration_style_id", lambda p: "Corpsdetexte")
    cfg = {"rendu": {"metadata": {"titre": "T", "auteur": "A", "langue": "fr"},
                     "formats": ["docx"], "styles": {},
                     "reference_docx": "templates/reference.docx"},
           "chemins": {}}
    R.render(md, tmp_path, cfg)
    assert cmds
    assert not any(a.startswith("keywords=") for a in cmds[0])
    # title/author/lang, eux, restent bien passés en --metadata (prioritaires sur le YAML)
    assert "title=T" in cmds[0] and "author=A" in cmds[0] and "lang=fr" in cmds[0]


@pytest.mark.skipif(shutil.which("pandoc") is None, reason="Pandoc non installé")
def test_version_reaches_docx_and_epub_metadata_for_real(tmp_path):
    """Test d'INTÉGRATION, avec le vrai Pandoc : c'est le seul qui aurait attrapé le
    no-op silencieux de `--metadata keywords=…`. Vérifie l'empreinte là où un lecteur
    la trouvera vraiment — cp:keywords en DOCX, dc:subject en EPUB — et que titre et
    auteur n'ont pas été écrasés au passage."""
    import re
    import zipfile

    import pipeline.render as R
    from core.version import __version__

    racine = Path(__file__).resolve().parent.parent
    md = tmp_path / "Tome.md"
    md.write_text("# Chapitre 1\n\nDu texte de récit.\n", encoding="utf-8")
    cfg = {"rendu": {"metadata": {"titre": "Light Novel", "auteur": "Angelith Novel",
                                  "langue": "fr"},
                     "formats": ["docx", "epub"],
                     "styles": {"dialogue": "List Paragraph", "pensee": "Pensée"},
                     "reference_docx": str(racine / "templates" / "reference.docx"),
                     "epub_css": str(racine / "templates" / "epub.css")},
           "chemins": {}}
    produced = R.render(md, tmp_path, cfg)
    noms = {p.suffix for p in produced}
    assert {".docx", ".epub"} <= noms, produced

    empreinte = f"Angelith {__version__}"

    docx = next(p for p in produced if p.suffix == ".docx")
    core_xml = zipfile.ZipFile(docx).read("docProps/core.xml").decode("utf-8")
    assert re.search(rf"<cp:keywords>{re.escape(empreinte)}</cp:keywords>", core_xml), core_xml
    assert "Light Novel" in core_xml and "Angelith Novel" in core_xml

    epub = next(p for p in produced if p.suffix == ".epub")
    with zipfile.ZipFile(epub) as z:
        opf = z.read(next(n for n in z.namelist() if n.endswith(".opf"))).decode("utf-8")
    assert empreinte in re.findall(r"<dc:subject[^>]*>(.*?)</dc:subject>", opf), opf
    assert "Light Novel" in opf


def test_has_runaway_repetition_detects_loop():
    from pipeline.orchestrator import _has_runaway_repetition
    para = "Ceci est un long paragraphe de récit qui décrit une scène de combat intense et prolongée."
    assert _has_runaway_repetition("\n\n".join([para] * 4)) is True
    assert _has_runaway_repetition("\n\n".join([para, "Une autre phrase.", "Encore une."])) is False


def test_looks_like_style_guide_detects_leak():
    from pipeline.orchestrator import _looks_like_style_guide
    assert _looks_like_style_guide("# Guide de style — conventions générales\n\nTexte.") is True
    assert _looks_like_style_guide("Un guide touristique décrivait la ville.") is False


def test_center_image_paragraphs_centers_drawing():
    """Une image dans un paragraphe « Corps de texte » doit être centrée (jc=center
    inséré après le pStyle)."""
    from pipeline.render import _center_image_paragraphs
    doc = ('<w:p><w:pPr><w:pStyle w:val="Corpsdetexte" /></w:pPr>'
           '<w:r><w:drawing><wp:inline/></w:drawing></w:r></w:p>'
           '<w:p><w:pPr><w:pStyle w:val="Corpsdetexte" /></w:pPr>'
           '<w:r><w:t>Texte normal.</w:t></w:r></w:p>')
    out = _center_image_paragraphs(doc)
    assert out.count('<w:jc w:val="center"/>') == 1          # seul le paragraphe image
    assert '<w:pStyle w:val="Corpsdetexte" /><w:jc w:val="center"/>' in out


def test_words_after_last_image_and_truncation_signal():
    """Régression réelle (fin du Vol.3) : le traducteur s'arrête au marqueur d'image et
    perd tout le récit qui suit. On compte les mots après la DERNIÈRE image."""
    from pipeline.orchestrator import _words_after_last_image, _word_count
    ref = ("Texte.\n\n<!-- IMG: media/image12.png -->\n\nCette nuit-là, Margo tomba dans "
           "un sommeil profond, tandis qu'Odette caressait sa joue en se moquant d'elle.")
    trunc = "Texte traduit.\n\n<!-- IMG: media/image12.png -->"
    full = ref.replace("Texte.", "Texte traduit.")
    assert _words_after_last_image(ref) >= 12
    assert _words_after_last_image(trunc) == 0
    # signal de troncature : queue effondrée ET chute globale de longueur
    def truncated(out):
        rt = _words_after_last_image(ref)
        return (rt >= 12 and _words_after_last_image(out) < rt * 0.5
                and _word_count(out) < _word_count(ref) * 0.85)
    assert truncated(trunc) is True
    assert truncated(full) is False       # texte complet → pas de faux positif
