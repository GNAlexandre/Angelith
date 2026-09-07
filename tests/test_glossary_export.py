# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Alexandre Tournel

"""L'export du glossaire — `core/glossary_export.py` (lot 34, L34.4).

⚠ **Le test d'idempotence est le critère du lot** (`PLAN-34` critère 5), et il porte sur les
**glossaires réels du corpus** quand ils sont là. Sur une machine sans `sources/` — la CI en
est une — il retombe sur un glossaire fabriqué qui porte les mêmes formes que le corpus :
multi-cibles, `termes_source`, `variantes`, `interdits`, `force`, et une catégorie
`anglicismes` au schéma plat.
"""
from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from core import glossary, glossary_cibles, glossary_export as gx, glossary_import as gi

#: Le plus gros glossaire du corpus au 2026-09-05 : **manga D, 124 entrées, 38 359
#: octets** (cf. `docs/mesures/bibliotheque-2026-09-05.md` §3). Nommé ici pour que le chiffre
#: du document et celui du test ne puissent pas diverger en silence.
PLUS_GROS = "manga D"


#: ⚠ Résolu depuis `__file__`, pas depuis le dossier courant : un `pytest` lancé d'ailleurs
#: sauterait le test des glossaires RÉELS **en silence**, et le critère 5 du plan passerait
#: au vert sans avoir rien vérifié.
RACINE = Path(__file__).resolve().parents[1]


def _glossaires_reels() -> list[Path]:
    return sorted(RACINE.glob("sources/*/glossaire.yaml"))


GLOSSAIRE_FABRIQUE = {
    "personnages": [
        {"termes_source": ["魔王"], "role": "antagoniste",
         "description": "Souverain des armées du gouffre.", "a_romaniser": False,
         "cibles": {"fr": {"nom": "Roi-démon", "pluriel": "Rois-démons",
                           "genre": "masculin", "variantes": ["Maô"],
                           "interdits": ["Seigneur des démons"], "force": True},
                    "en": {"nom": "Demon King", "genre": "?"}}},
        {"termes_source": ["ミナ"], "description": "",
         "cibles": {"fr": {"nom": "Mina", "genre": "féminin", "variantes": [],
                           "interdits": [], "force": False}}},
    ],
    "termes": [
        {"termes_source": ["魔力"], "traduire": True, "description": "Énergie magique.",
         "cibles": {"fr": {"nom": "mana", "variantes": ["magie"], "interdits": [],
                           "force": False}}},
    ],
    "anglicismes": [{"vo": "OK", "fr": "d'accord"}],
    "groupes": [{"nom": "les jumelles", "note": "accord au féminin pluriel"}],
}


@pytest.fixture()
def source(tmp_path: Path) -> Path:
    chemin = tmp_path / "glossaire.yaml"
    chemin.write_text(yaml.safe_dump(GLOSSAIRE_FABRIQUE, allow_unicode=True,
                                     sort_keys=False), encoding="utf-8")
    return chemin


# --------------------------------------------------------------------------- #
#  Le format d'ARCHIVE
# --------------------------------------------------------------------------- #

def test_le_yaml_est_le_seul_format_d_archive():
    assert gx.est_archive("yaml")
    assert not gx.est_archive("csv")
    assert not gx.est_archive("md")
    assert gx.PERTES["yaml"] == ()
    assert gx.PERTES["csv"] and gx.PERTES["md"]


def test_l_aller_retour_yaml_est_idempotent_sur_un_glossaire_fabrique(source, tmp_path):
    avant = gi.lire_glossaire_yaml(source, "fr")[0]
    dest = gx.exporter(source, tmp_path / "export.yaml", "yaml", projet="Œuvre", tome="Vol.1")
    apres = gi.lire_glossaire_yaml(dest, "fr")[0]
    assert apres == avant


def test_l_export_yaml_garde_les_AUTRES_langues_cibles(source, tmp_path):
    """⚠ L'invariant central du format multi-cibles : exporter un glossaire vers le français
    ne doit pas effacer le travail fait en anglais."""
    dest = gx.exporter(source, tmp_path / "export.yaml", "yaml", projet="Œuvre", cible="fr")
    brut = yaml.safe_load(dest.read_text(encoding="utf-8"))
    assert glossary_cibles.cibles_presentes(brut) == ["en", "fr"]
    assert brut["personnages"][0]["cibles"]["en"]["nom"] == "Demon King"


def test_l_export_ne_touche_jamais_sa_source(source, tmp_path):
    """⚠ `glossary.load` MIGRE et RÉÉCRIT le fichier qu'il ouvre. Exporter est une lecture."""
    avant = source.read_bytes()
    for format in ("yaml", "csv", "md"):
        gx.exporter(source, tmp_path / f"e{format}", format, projet="Œuvre")
    assert source.read_bytes() == avant


@pytest.mark.skipif(not _glossaires_reels(),
                    reason="pas de corpus sous sources/ (c'est le cas en CI)")
def test_l_aller_retour_yaml_est_idempotent_sur_les_glossaires_REELS(tmp_path):
    """**Le critère 5 du `PLAN-34`**, sur les glossaires du corpus, structure contre
    structure — jamais octet contre octet, l'en-tête de provenance étant justement neuf."""
    reels = _glossaires_reels()
    assert len(reels) >= 10, "corpus incomplet : le test perdrait son sens"
    for chemin in reels:
        projet = chemin.parent.name
        avant_octets = chemin.read_bytes()
        attendu = gi.lire_glossaire_yaml(chemin, "fr")[0]
        dest = gx.exporter(chemin, tmp_path / f"{projet}.yaml", "yaml", projet=projet)
        assert gi.lire_glossaire_yaml(dest, "fr")[0] == attendu, projet
        assert chemin.read_bytes() == avant_octets, f"{projet} : la source a été modifiée"


@pytest.mark.skipif(not _glossaires_reels(),
                    reason="pas de corpus sous sources/ (c'est le cas en CI)")
def test_le_plus_gros_glossaire_du_corpus_est_bien_celui_qui_est_documente():
    """La règle des chiffres : le document de mesure NOMME le plus gros glossaire, ce test
    refuse que le nom vieillisse sans qu'on le voie."""
    comptes = {p.parent.name: gx.compter(gx.lire_brut(p)) for p in _glossaires_reels()}
    assert max(comptes, key=comptes.get) == PLUS_GROS
    assert comptes[PLUS_GROS] >= 100


# --------------------------------------------------------------------------- #
#  Les VUES : la perte est nommée DANS le fichier
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("format", ["csv", "md"])
def test_une_vue_ecrit_sa_perte_et_sa_provenance_dans_le_fichier(source, tmp_path, format):
    """Critère 6 : sans ça, quelqu'un le réimportera dans six mois et perdra ses accords."""
    dest = gx.exporter(source, tmp_path / f"vue.{format}", format,
                       projet="Mon Œuvre", tome="Vol.3", cible="fr")
    texte = dest.read_text(encoding="utf-8-sig")
    assert "VUE, PAS ARCHIVE" in texte
    for perte in gx.PERTES[format]:
        # Le premier fragment suffit : le texte est reformaté par la mise en page.
        assert perte.format(cible="fr").split(" :")[0].split(" —")[0] in texte
    # La provenance, en entier — c'est la règle des chiffres appliquée à un fichier qui va
    # circuler : un glossaire sans dénominateur ne se fusionne pas.
    from core.version import __version__
    assert "Mon Œuvre" in texte and "Vol.3" in texte
    assert __version__ in texte
    # 2 personnages + 1 terme + 1 anglicisme + 1 groupe.
    assert "5 entrée(s)" in texte
    assert "« fr »" in texte


def test_le_yaml_porte_sa_provenance_sans_annoncer_de_perte(source, tmp_path):
    dest = gx.exporter(source, tmp_path / "a.yaml", "yaml", projet="Mon Œuvre", tome="Vol.3")
    texte = dest.read_text(encoding="utf-8")
    assert "VUE, PAS ARCHIVE" not in texte
    assert "Format d'ARCHIVE" in texte
    assert "Mon Œuvre" in texte


# --------------------------------------------------------------------------- #
#  Le CSV se réimporte — et son en-tête ne devient pas des entrées fantômes
# --------------------------------------------------------------------------- #

def test_l_entete_de_perte_ne_se_reimporte_pas_en_fausses_entrees(source, tmp_path):
    """⚠ Le défaut que ce lot corrige dans `glossary_import` : une ligne de commentaire
    contenant « : » ou « — » était découpée en paire terme → traduction, si bien que
    l'avertissement lui-même devenait une entrée de glossaire."""
    dest = gx.exporter(source, tmp_path / "vue.csv", "csv", projet="Mon Œuvre", cible="fr")
    relu = gi.parse_file(dest)
    noms = {e.get("nom") or e.get("vo") for cat in glossary.ORDER
            for e in (relu.get(cat) or [])}
    assert noms == {"Roi-démon", "Mina", "mana", "OK", "les jumelles"}
    assert not any("Angelith" in (n or "") for n in noms)


def test_le_csv_rend_les_categories_les_genres_et_les_listes(source, tmp_path):
    dest = gx.exporter(source, tmp_path / "vue.csv", "csv", projet="Mon Œuvre", cible="fr")
    relu = gi.parse_file(dest)
    roi = next(e for e in relu["personnages"] if e["nom"] == "Roi-démon")
    assert roi["genre"] == "masculin"
    assert roi["variantes"] == ["Maô"]
    assert roi["interdits"] == ["Seigneur des démons"]
    assert roi["force"] is True
    assert roi["termes_source"] == ["魔王"]
    assert relu["anglicismes"] == [{"vo": "OK", "fr": "d'accord"}]
    assert relu["groupes"] == [{"nom": "les jumelles", "note": "accord au féminin pluriel"}]


def test_le_csv_perd_exactement_ce_qu_il_annonce(source, tmp_path):
    """La perte du CSV est **nommée** ; ce test vérifie qu'elle est aussi **exacte** — ni
    plus (on annoncerait une perte qui n'existe pas), ni moins (on en cacherait une)."""
    dest = gx.exporter(source, tmp_path / "vue.csv", "csv", projet="Mon Œuvre", cible="fr")
    relu = gi.parse_file(dest)
    roi = next(e for e in relu["personnages"] if e["nom"] == "Roi-démon")
    # annoncé perdu : les autres cibles, et les champs hors colonnes
    assert "cibles" not in roi
    assert "a_romaniser" not in roi
    # annoncé CONSERVÉ : tout le reste de la cible exportée
    assert roi["role"] == "antagoniste"
    assert roi["pluriel"] == "Rois-démons"
    assert roi["description"] == "Souverain des armées du gouffre."


def test_un_csv_ecrit_a_la_main_retombe_sur_le_parseur_tolerant(tmp_path):
    """⚠ On ne prend la main que sur ce qu'on reconnaît : un `.csv` de quelqu'un d'autre est
    presque toujours un tableau à deux colonnes, que le parseur tolérant lit mieux.

    Il **échouait** avant ce lot : `.csv` levait « Format non géré », alors que
    `gui/depot.py` l'annonçait importable depuis le lot 18."""
    chemin = tmp_path / "a_la_main.csv"
    chemin.write_text("Maou\tRoi-démon\nMana\tMana\n", encoding="utf-8")
    relu = gi.parse_file(chemin)
    assert {t["nom"] for t in relu["termes"]} == {"Maou", "Mana"}


def test_un_csv_sans_entete_reconnu_ne_leve_pas(tmp_path):
    chemin = tmp_path / "vide.csv"
    chemin.write_text("# rien que des commentaires\n", encoding="utf-8")
    assert gi.parse_file(chemin) == {"termes": [], "personnages": [], "anglicismes": []}


def test_le_markdown_ne_reimporte_pas_sa_provenance(source, tmp_path):
    """La citation Markdown est de la prose, toujours — et c'est sous cette forme que
    l'export porte sa liste de pertes."""
    dest = gx.exporter(source, tmp_path / "vue.md", "md", projet="Mon Œuvre", cible="fr")
    relu = gi.parse_file(dest)
    noms = {(e.get("nom") or e.get("vo") or "") for cat in ("termes", "personnages",
                                                            "anglicismes")
            for e in (relu.get(cat) or [])}
    assert not any("glossaire est propre" in n.lower() for n in noms)
    assert "Roi-démon" in noms


# --------------------------------------------------------------------------- #
#  Détails
# --------------------------------------------------------------------------- #

def test_un_format_inconnu_est_refuse(source, tmp_path):
    with pytest.raises(ValueError, match="format d'export inconnu"):
        gx.exporter(source, tmp_path / "x.txt", "docx", projet="Œuvre")


def test_le_nom_propose_se_retrouve_dans_un_dossier_de_telechargements():
    nom = gx.nom_propose("roman Q", "Vol.1", "yaml", date="2026-09-05")
    assert nom == "roman Q_Vol.1_glossaire_2026-09-05.yaml"
    # Aucun caractère qu'un système de fichiers refuserait.
    assert not set(nom) & set('<>:"/\\|?*')


def test_un_glossaire_vide_s_exporte_sans_lever(tmp_path):
    source = tmp_path / "vide.yaml"
    source.write_text("# rien\n", encoding="utf-8")
    for format in ("yaml", "csv", "md"):
        dest = gx.exporter(source, tmp_path / f"v.{format}", format, projet="Œuvre")
        assert "0 entrée(s)" in dest.read_text(encoding="utf-8-sig")
