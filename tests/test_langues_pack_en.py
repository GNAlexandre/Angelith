# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Alexandre Tournel

"""Le pack anglais livré — la preuve que l'architecture tient.

Ce fichier ne juge pas la QUALITÉ des prompts anglais : cela ne se teste pas, cela se relit.
Il verrouille ce qui casserait en silence :

1. le pack est **complet et résoluble** — sept consignes déclarées, huit prompts présents ;
2. sa typographie **segmente réellement de l'anglais**, ce que le motif français ne fait pas ;
3. le format de sortie de son terminologue est **relu par le parseur de glossaire**, alors
   qu'il est écrit en anglais.

Le troisième est le moins visible et le plus grave : un glossaire qui ne se parse pas ressort
VIDE, sans qu'aucun compteur ne s'en aperçoive.
"""
from pathlib import Path

import pytest
import yaml

from core import glossary_build, langues
from pipeline import render
from pipeline import typographie as ty

RACINE = Path(__file__).resolve().parent.parent
GUILLEMET_OUVRANT, GUILLEMET_FERMANT = "“", "”"


@pytest.fixture
def pack_en(monkeypatch):
    monkeypatch.chdir(RACINE)
    return langues.resoudre_pack({"langues": {"cible": "en"}})


# ─────────────────────────────────────────────────────────────────────────────
# 1. Le pack est complet
# ─────────────────────────────────────────────────────────────────────────────

def test_le_pack_en_se_resout(pack_en):
    assert pack_en.code == "en"
    assert pack_en.nom_lisible() == "English"
    assert pack_en.racine is not None


def test_les_huit_prompts_sont_la(pack_en):
    """`resoudre_pack` refuserait déjà un pack amputé ; ce test nomme le fichier fautif."""
    manquants = [n for n in langues.PROMPTS_REQUIS if not pack_en.prompt(n).exists()]

    assert manquants == []


def test_les_sept_consignes_sont_declarees(pack_en):
    """⚠ Le point le plus facile à rater. Une consigne non déclarée retombe sur le texte
    FRANÇAIS resté au site d'appel — donc une instruction française au milieu d'un run
    anglais, ce qui ne lève rien et ne se voit que dans la sortie."""
    manquantes = [c for c in langues.CONSIGNES_CONNUES if c not in pack_en.consignes]

    assert manquantes == []


@pytest.mark.parametrize("cle", langues.CONSIGNES_CONNUES)
def test_aucune_consigne_anglaise_ne_retombe_sur_le_francais(pack_en, cle):
    assert pack_en.consigne(cle, "REPLI FRANÇAIS") != "REPLI FRANÇAIS"


def test_le_guide_de_style_et_le_css_sont_fournis(pack_en):
    assert pack_en.fichier("style_guide.md") is not None
    assert pack_en.fichier("templates/epub.css") is not None


def test_le_titre_du_guide_declare_correspond_au_fichier(pack_en):
    """Le garde-fou « le modèle a régurgité le guide » cherche ce titre. Une divergence entre
    `pack.yaml` et l'en-tête réel du fichier rendrait le garde-fou muet."""
    typo = ty.Typographie.depuis_pack(pack_en)
    premiere = pack_en.fichier("style_guide.md").read_text(encoding="utf-8").splitlines()[0]

    assert typo.guide_de_style.search(premiere), premiere


# ─────────────────────────────────────────────────────────────────────────────
# 2. La typographie segmente vraiment de l'anglais
# ─────────────────────────────────────────────────────────────────────────────

def _blocs(texte, typo):
    return render._segment_text(texte, "List Paragraph", typo) or []


def _dialogue(blocs):
    return [b.splitlines()[1] for b in blocs if ".dialogue" in b]


def _narration(blocs):
    return [b for b in blocs if ".dialogue" not in b]


@pytest.mark.parametrize("texte,attendu", [
    # Sujet d'abord — la forme ORDINAIRE en anglais, et celle que le motif français rate.
    (f"{GUILLEMET_OUVRANT}Go!{GUILLEMET_FERMANT} she shouted, charging; their blades met.",
     "Go! she shouted, charging;"),
    # Verbe d'abord — l'anglais l'admet aussi.
    (f"{GUILLEMET_OUVRANT}Go!{GUILLEMET_FERMANT} shouted the girl. The wind rose.",
     "Go! shouted the girl."),
    # Titre + nom propre + verbe.
    (f"{GUILLEMET_OUVRANT}Listen.{GUILLEMET_FERMANT} Captain Vance replied. Silence fell.",
     "Listen. Captain Vance replied."),
])
def test_lincise_anglaise_reste_collee(pack_en, texte, attendu):
    """⚠ C'est l'adaptation qui justifie que `verbes_de_parole` soit une FONCTION du pack.

    Le français inverse et met le verbe en tête (« dit-il ») ; l'anglais ne l'inverse pas et
    commence par le SUJET (`she said`). Un motif ancré sur le verbe ne collerait donc presque
    aucune incise anglaise, et chacune partirait en paragraphe de narration."""
    typo = ty.Typographie.depuis_pack(pack_en)

    assert _dialogue(_blocs(texte, typo)) == [attendu]


def test_la_narration_ordinaire_nest_pas_collee(pack_en):
    typo = ty.Typographie.depuis_pack(pack_en)
    texte = (f"{GUILLEMET_OUVRANT}Go!{GUILLEMET_FERMANT} The girl raised her weapon. "
             f"{GUILLEMET_OUVRANT}Listen to me!{GUILLEMET_FERMANT}")

    blocs = _blocs(texte, typo)

    assert _dialogue(blocs) == ["Go!", "Listen to me!"]
    assert [n.strip() for n in _narration(blocs)] == ["The girl raised her weapon."]


def test_le_motif_francais_ne_voit_rien_dans_de_langlais():
    """La contre-épreuve, et la raison d'être de tout le lot : sans pack, le rendu ne
    reconnaît aucune réplique anglaise — les guillemets français n'y sont pas."""
    texte = f"{GUILLEMET_OUVRANT}Go!{GUILLEMET_FERMANT} she shouted. The wind rose."

    assert render._segment_text(texte, "List Paragraph", ty.DEFAUT) is None


def test_le_css_anglais_najoute_pas_de_tiret(pack_en):
    """Une réplique anglaise est délimitée par ses guillemets, que le texte porte déjà.
    Un `::before` de tiret par-dessus donnerait « — “Go!” »."""
    import re

    css = pack_en.fichier("templates/epub.css").read_text(encoding="utf-8")
    # Les COMMENTAIRES sont retirés : celui de la règle explique précisément pourquoi il n'y
    # a pas de `::before`, et le chercher dans le texte brut trouverait sa propre explication.
    regles = re.sub(r"/\*.*?\*/", "", css, flags=re.S)

    assert "::before" not in regles
    assert ".dialogue p {" in regles


# ─────────────────────────────────────────────────────────────────────────────
# 3. Le glossaire anglais se parse — le point le moins visible
# ─────────────────────────────────────────────────────────────────────────────

NOTES_ANGLAISES = """### CHARACTERS
- Elias Vance | gender: male | variants: Eli | source_terms: ヴァンス | Fourth officer.
### PLACES
- Lyell | source_terms: リエル | A walled trading city.
### ORGANIZATIONS
- The Iron Concord | A merchant alliance.
### CREATURES
- Fenwisp | gender: female | A marsh spirit.
### ITEMS
- Sunreaver | translate: no | A relic blade.
### TERMS
- Markless | forbidden: No-Mark | translate: yes | Born without a guild sigil.
### EVENTS
- The Long Frost | A winter that lasted three years.
### LOANWORDS
- déjà-vu → the same feeling again
"""


def test_les_sections_anglaises_sont_reconnues():
    """⚠ Sans les alias anglais de `_CAT_KEYS`, ces sections tombent toutes dans la même
    catégorie par défaut — et le glossaire d'un tome anglais ressort inexploitable."""
    g = glossary_build.parse_notes(NOTES_ANGLAISES)

    for cat in ("personnages", "lieux", "organisations", "creatures", "objets",
                "termes", "evenements"):
        assert len(g.get(cat) or []) == 1, cat
    assert len(g.get("anglicismes") or []) == 1


def test_les_champs_anglais_sont_ramenes_au_schema():
    """Le schéma du glossaire reste FRANÇAIS (`genre`, `variantes`, `termes_source`) : les
    alias traduisent le nom du champ, jamais le format du fichier."""
    g = glossary_build.parse_notes(NOTES_ANGLAISES)
    elias = g["personnages"][0]

    assert elias["nom"] == "Elias Vance"
    assert elias["genre"] == "masculin"
    assert elias["variantes"] == ["Eli"]
    assert elias["termes_source"] == ["ヴァンス"]
    assert g["termes"][0]["interdits"] == ["No-Mark"]
    assert g["termes"][0]["traduire"] is True
    assert g["objets"][0]["traduire"] is False


def test_le_format_du_prompt_terminologue_est_celui_que_le_parseur_lit():
    """Garde-fou contre la dérive : les en-têtes ÉCRITS dans le prompt anglais doivent être
    ceux que `_CAT_KEYS` sait reconnaître. Les recopier à la main dans deux fichiers est
    exactement le genre d'accord qui se défait sans bruit."""
    prompt = (RACINE / "langues" / "en" / "prompts" / "terminologue.md").read_text(
        encoding="utf-8")
    entetes = [ligne[4:].strip() for ligne in prompt.splitlines()
               if ligne.startswith("### ")]

    assert entetes, "aucun en-tête de section dans le prompt"
    for entete in entetes:
        assert glossary_build._header_to_cat(entete) is not None, entete


def test_le_pack_en_est_un_yaml_valide_et_complet():
    meta = yaml.safe_load((RACINE / "langues" / "en" / "pack.yaml").read_text(encoding="utf-8"))

    assert meta["code"] == "en"
    assert meta["nom"]
    assert set(meta["consignes"]) == set(langues.CONSIGNES_CONNUES)
    assert meta["typographie"]["verbes_de_parole"]
