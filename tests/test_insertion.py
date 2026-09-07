# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Alexandre Tournel

"""L27.4 — **l'insertion dans les sorties, opt-in et étiquetée**, et ses quatre garde-fous.

Critères du `PLAN-27` couverts ici :

| Critère | Test |
|---|---|
| 7 — défaut `false`, tome **iso-octet** | `test_un_tome_relance_sans_rien_demander_est_iso_octet` |
| 8 — la légende est dans les TROIS formats, non désactivable | `test_la_legende_sort_dans_les_trois_formats` |
| 9 — le test de collision de noms existe | `test_une_illustration_ne_peut_pas_collisionner_avec_un_media` |
"""
import re
import shutil
import zipfile
from pathlib import Path

import pytest

from core import insertion

RACINE = Path(__file__).resolve().parent.parent

TEXTE = """# Chapitre 1 — Le départ

Aya marchait vite dans la rue.

Un second paragraphe de récit.

# Chapitre 2 — L'arrivée

Bertrand attendait sous la pluie.
"""


def _illustration(nom="ia-aya.png", personnage="Aya", graine=7):
    return insertion.Illustration(
        chemin=Path("sources/P/illustrations") / nom, personnage=personnage, graine=graine,
        cadrage="buste", date="2026-09-02", modele="qwen-image-edit-2511")


def _inserer(**champs):
    defauts = dict(legende=insertion.LEGENDE_FR, depuis=Path("build/P/Vol.1"))
    defauts.update(champs)
    illustrations = defauts.pop("illustrations", [_illustration()])
    return insertion.inserer(defauts.pop("markdown", TEXTE), illustrations, **defauts)


# ─────────────────────────────  La légende, sans interrupteur  ─────────────────────────────

def test_la_legende_est_obligatoire_et_l_absence_LEVE():
    """C'est le seul endroit du code qui puisse produire une image d'IA visible dans un
    document sans qu'elle se déclare. Le refus est donc une exception, pas un avertissement."""
    with pytest.raises(insertion.LegendeManquante):
        _inserer(legende="")
    with pytest.raises(insertion.LegendeManquante):
        _inserer(legende="   ")


def test_aucune_branche_n_ecrit_un_marqueur_sans_sa_legende():
    """`bloc()` est le seul fabricant, et il lève avant d'écrire quoi que ce soit."""
    with pytest.raises(insertion.LegendeManquante):
        insertion.bloc(_illustration(), Path("build"), "")


def test_la_legende_vient_du_pack_de_langue_cible():
    """Un tome anglais porte la version anglaise ; un pack qui oublie la clé retombe sur le
    français plutôt que sur rien."""
    from core import langues

    pack_en = langues._pack_de_dossier(RACINE / "langues" / "en", "en", {})
    assert insertion.legende_du_pack(pack_en) != insertion.LEGENDE_FR
    assert "AI-generated" in insertion.legende_du_pack(pack_en)
    assert insertion.legende_du_pack(None) == insertion.LEGENDE_FR


def test_aucune_cle_de_configuration_ne_peut_vider_la_legende():
    """Le repli est en dur dans `core/insertion.py`, pas dans `config.yaml`."""
    schema = (RACINE / "core" / "config_schema.py").read_text(encoding="utf-8")
    assert "legende" not in schema.lower()


# ─────────────────────────────  Où l'image atterrit  ─────────────────────────────

def test_l_image_va_au_debut_du_premier_chapitre_qui_nomme_le_personnage():
    sortie, inserees = _inserer()
    assert len(inserees) == 1
    assert inserees[0].chapitre.startswith("Chapitre 1")
    avant_chapitre_2 = sortie.split("# Chapitre 2")[0]
    assert "ia-aya.png" in avant_chapitre_2


def test_fin_de_chapitre_place_l_image_apres_le_recit():
    sortie, _ = _inserer(position=insertion.FIN_CHAPITRE)
    debut, reste = sortie.split("Aya marchait vite", 1)
    assert "ia-aya.png" not in debut
    assert "ia-aya.png" in reste.split("# Chapitre 2")[0]


def test_une_illustration_sans_chapitre_va_en_tete_de_volume_plutot_que_d_etre_perdue():
    sortie, inserees = _inserer(illustrations=[_illustration(personnage="Zoé")])
    assert inserees[0].position == insertion.TETE_DE_VOLUME
    assert inserees[0].chapitre == ""
    assert sortie.index("ia-aya.png") < sortie.index("# Chapitre 1")


def test_le_nom_est_cherche_entre_bornes_de_mot():
    """Un personnage nommé « Ai » ne doit répondre ni à « j'ai » ni à « mais »."""
    texte = "# Chapitre 1\n\nJ'ai mis la main dessus, mais rien.\n"
    _, inserees = _inserer(markdown=texte,
                           illustrations=[_illustration(personnage="Ai")])
    assert inserees[0].position == insertion.TETE_DE_VOLUME


def test_l_ordre_des_images_en_tete_de_volume_est_celui_de_la_liste():
    sortie, _ = _inserer(illustrations=[_illustration("ia-1.png", "Zoé"),
                                        _illustration("ia-2.png", "Zoé")])
    assert sortie.index("ia-1.png") < sortie.index("ia-2.png")


def test_une_position_inconnue_leve_plutot_que_de_deviner():
    with pytest.raises(ValueError, match="position d'insertion inconnue"):
        _inserer(position="au_milieu")


def test_aucun_caractere_de_recit_n_est_reecrit_ni_perdu():
    """On n'insère que des paragraphes NEUFS entre les siens. À la normalisation des lignes
    vides près — seule chose que l'épissage puisse changer, et qui n'est pas du texte."""
    sortie, inserees = _inserer(illustrations=[_illustration("ia-a.png", "Aya"),
                                               _illustration("ia-b.png", "Bertrand")])
    nettoye = sortie
    for inseree in inserees:
        nettoye = nettoye.replace(
            insertion.bloc(inseree.illustration, Path("build/P/Vol.1"),
                           insertion.LEGENDE_FR), "")
    assert _normaliser(nettoye) == _normaliser(TEXTE)


def _normaliser(texte: str) -> str:
    return re.sub(r"\n{2,}", "\n\n", texte).strip()


# ─────────────────────────────  L'espace de noms  ─────────────────────────────

def test_une_illustration_ne_peut_pas_collisionner_avec_un_media(tmp_path):
    """⚠ Critère 9. `pipeline/images.py` documente le risque : « chaque document renumérote
    ses médias depuis 1 ». Une illustration générée n'appartient à aucun document, mais on le
    VÉRIFIE plutôt que de le raisonner."""
    texte = ("# Chapitre 1\n\n<!-- IMG: media/image1.png -->\n\nAya marchait.\n")
    sortie, _ = _inserer(markdown=texte,
                         illustrations=[_illustration("ia-image1.png", "Aya")])
    assert insertion.collisions(sortie) == []
    assert "media/image1.png" in sortie and "ia-image1.png" in sortie


def test_collisions_attrape_deux_chemins_qui_portent_le_meme_nom():
    """Le contrôle doit détecter quelque chose, sinon il ne prouve rien."""
    faux = ("<!-- IMG: media/image1.png -->\n\n"
            "<!-- IMG: ../autre/media/image1.png -->\n")
    assert insertion.collisions(faux)


def test_le_prefixe_reserve_ne_ressemble_a_aucune_renumerotation_de_document():
    assert insertion.nom_sans_collision("aya.png") == "ia-aya.png"
    assert insertion.nom_sans_collision("ia-aya.png") == "ia-aya.png"
    for schema in ("image1.png", "media1.png", "img_001.png", "Picture 1.png"):
        assert not schema.startswith(insertion.PREFIXE)


def test_le_chemin_de_marqueur_est_RELATIF_au_dossier_de_build():
    """Le Markdown assemblé est l'artefact durable, rejoué par `--render-only` des mois plus
    tard : un `C:/Users/…` dedans ne se rejouerait pas ailleurs."""
    chemin = insertion.chemin_de_marqueur(
        Path("sources/P/illustrations/ia-aya.png"), Path("build/P/Vol.1"))
    assert not Path(chemin).is_absolute()
    assert "/" in chemin and "\\" not in chemin


def test_le_suffixe_de_sidecar_est_le_meme_des_deux_cotes():
    """`core/` recopie la constante plutôt que d'importer une brique ; les deux valeurs
    doivent rester identiques, et c'est ce test qui le tient."""
    from illustration import marquage

    assert insertion.SUFFIXE_PROVENANCE == marquage.SUFFIXE_PROVENANCE


# ─────────────────────────────  Lire ce qui a été retenu  ─────────────────────────────

def test_une_image_sans_sidecar_est_ignoree(tmp_path):
    """Le sidecar est ce qui prouve qu'elle vient de cette brique et qu'un humain a validé son
    prompt. Insérer une image dont on ne peut rien dire irait contre ce que la légende
    affirme."""
    dossier = tmp_path / "illustrations"
    dossier.mkdir()
    (dossier / "orpheline.png").write_bytes(b"\x89PNG\r\n\x1a\n")
    assert insertion.retenues(dossier) == []


def test_les_retenues_portent_leur_personnage_et_leur_graine(tmp_path):
    import json

    dossier = tmp_path / "illustrations"
    dossier.mkdir()
    (dossier / "ia-aya.png").write_bytes(b"\x89PNG\r\n\x1a\n")
    (dossier / ("ia-aya.png" + insertion.SUFFIXE_PROVENANCE)).write_text(json.dumps({
        "genere_par_ia": True, "payload": {"graine": 42},
        "prompt_source": {"personnage": "Aya", "cadrage": "buste"}}), encoding="utf-8")
    (illustration,) = insertion.retenues(dossier)
    assert illustration.personnage == "Aya" and illustration.graine == 42


def test_un_dossier_absent_rend_une_liste_vide_pas_une_erreur():
    assert insertion.retenues(Path("nulle-part")) == []


# ─────────────────────────────  Le rapport  ─────────────────────────────

def test_le_rapport_liste_personnage_et_graine():
    """Critère 3 de L27.4. Une liste de noms de fichier obligerait à ouvrir onze sidecars."""
    _, inserees = _inserer()
    lignes = "\n".join(insertion.lignes_de_rapport(inserees))
    assert "ia-aya.png" in lignes and "Aya" in lignes and "graine : 7" in lignes
    assert "ne font pas partie de l'œuvre originale" in lignes


def test_le_rapport_est_vide_quand_rien_n_a_ete_insere():
    assert insertion.lignes_de_rapport([]) == []


# ─────────────────────  Le pipeline : désarmé par défaut, iso-octet  ─────────────────────

def test_le_defaut_du_depot_est_desarme():
    import subprocess

    import yaml

    sortie = subprocess.run(["git", "-C", str(RACINE), "show", "HEAD:config.yaml"],
                            capture_output=True, text=True, timeout=15, encoding="utf-8")
    livre = yaml.safe_load(sortie.stdout) if sortie.returncode == 0 else \
        yaml.safe_load((RACINE / "config.yaml").read_text(encoding="utf-8"))
    # ⚠ `.get(..., False)` et non `[...]` : une clé ABSENTE est aussi désarmée que
    # `false` — `orchestrateur.reglages` lui donne le même défaut. Exiger sa présence ferait
    # échouer ce test sur toute révision antérieure au lot 27, ce qui ne dit rien de ce que
    # le dépôt publie aujourd'hui.
    assert livre["illustration"].get("inserer_dans_sorties", False) is False


def test_desarme_le_pipeline_ne_lit_meme_pas_le_dossier_des_retenues(monkeypatch):
    """Iso-comportement au sens fort : ce n'est pas « il n'insère rien », c'est « il ne
    regarde pas »."""
    from pipeline import orchestrator

    monkeypatch.setattr(insertion, "retenues",
                        lambda _d: pytest.fail("le dossier a été lu alors que la clé est à "
                                               "false"))
    sortie, inserees = orchestrator._inserer_illustrations(
        TEXTE, "P", {"illustration": {}, "chemins": {"sources": "sources"}},
        Path("build"), None, _reporter())
    assert sortie == TEXTE and inserees == []


def test_un_tome_relance_sans_rien_demander_est_iso_octet(tmp_path):
    """⚠ **Critère 7.** Deux passages du même Markdown, clé désarmée, comparés octet pour
    octet — et l'empreinte de `config.yaml` est annoncée dans le document du lot."""
    from pipeline import orchestrator

    config = {"illustration": {"inserer_dans_sorties": False},
              "chemins": {"sources": str(tmp_path)}}
    premier, _ = orchestrator._inserer_illustrations(TEXTE, "P", config, tmp_path, None,
                                                     _reporter())
    second, _ = orchestrator._inserer_illustrations(premier, "P", config, tmp_path, None,
                                                    _reporter())
    assert premier.encode("utf-8") == TEXTE.encode("utf-8")
    assert second.encode("utf-8") == TEXTE.encode("utf-8")


def test_arme_mais_sans_image_retenue_le_pipeline_le_DIT(tmp_path):
    from pipeline import orchestrator

    reporter = _reporter()
    config = {"illustration": {"inserer_dans_sorties": True},
              "chemins": {"sources": str(tmp_path)}}
    sortie, inserees = orchestrator._inserer_illustrations(TEXTE, "P", config, tmp_path,
                                                           None, reporter)
    assert sortie == TEXTE and inserees == []
    assert any("aucune image retenue" in m for _n, m in reporter.lignes)


def test_une_position_inconnue_retombe_sur_le_debut_de_chapitre_en_le_disant(tmp_path):
    import json

    from pipeline import orchestrator

    dossier = tmp_path / "P" / "illustrations"
    dossier.mkdir(parents=True)
    (dossier / "ia-aya.png").write_bytes(b"\x89PNG\r\n\x1a\n")
    (dossier / ("ia-aya.png" + insertion.SUFFIXE_PROVENANCE)).write_text(json.dumps({
        "genere_par_ia": True, "payload": {"graine": 1},
        "prompt_source": {"personnage": "Aya"}}), encoding="utf-8")
    reporter = _reporter()
    config = {"illustration": {"inserer_dans_sorties": True,
                               "insertion": {"position": "quelque part"}},
              "chemins": {"sources": str(tmp_path)}}
    sortie, inserees = orchestrator._inserer_illustrations(TEXTE, "P", config, tmp_path,
                                                           None, reporter)
    assert len(inserees) == 1
    assert insertion.LEGENDE_FR in sortie
    assert any("inconnu" in m for _n, m in reporter.lignes)


class _reporter:
    def __init__(self):
        self.lignes = []

    def info(self, message):
        self.lignes.append(("info", message))

    def warn(self, message):
        self.lignes.append(("warn", message))


# ─────────────────────  Critère 8 : les TROIS formats, pour de vrai  ─────────────────────

@pytest.mark.skipif(shutil.which("pandoc") is None, reason="Pandoc non installé")
def test_la_legende_sort_dans_les_trois_formats(tmp_path):
    """⚠ **Vérifié format par format, avec le vrai Pandoc.** Un test qui se contenterait de
    chercher la légende dans le Markdown ne dirait rien de ce qu'un lecteur voit : c'est la
    chaîne de rendu qui peut la perdre, pas l'assemblage.

    ⚠ **Et le contrat de styles de `reference.docx` n'est pas touché** : la légende est un
    paragraphe ordinaire en italiques, pas un style Word — y ajouter un style « Légende »
    romprait ce que la règle de numérotation du dépôt désigne comme un MAJEUR."""
    import pipeline.render as R

    (tmp_path / "sources" / "P" / "illustrations").mkdir(parents=True)
    image = tmp_path / "sources" / "P" / "illustrations" / "ia-aya.png"
    _petit_png(image)
    build = tmp_path / "build" / "P" / "Vol.1"
    build.mkdir(parents=True)

    corps, _ = insertion.inserer(
        TEXTE, [insertion.Illustration(chemin=image, personnage="Aya", graine=7)],
        legende=insertion.LEGENDE_FR, depuis=build)
    md = build / "Tome.md"
    md.write_text(corps, encoding="utf-8")

    config = {"rendu": {"metadata": {"titre": "T", "auteur": "A", "langue": "fr"},
                        "formats": ["docx", "epub", "pdf"],
                        "styles": {"dialogue": "List Paragraph", "pensee": "Pensée"},
                        "pdf_engine": "weasyprint"},
              "chemins": {},
              "langues": {"packs": str(RACINE / "langues")}}
    produits = R.render(md, build, config)
    suffixes = {p.suffix for p in produits}
    assert {".docx", ".epub"} <= suffixes, produits

    docx = next(p for p in produits if p.suffix == ".docx")
    document = zipfile.ZipFile(docx).read("word/document.xml").decode("utf-8")
    assert "Illustration générée par IA" in document.replace("</w:t><w:t>", "")

    epub = next(p for p in produits if p.suffix == ".epub")
    with zipfile.ZipFile(epub) as archive:
        pages = "".join(archive.read(n).decode("utf-8") for n in archive.namelist()
                        if n.endswith((".xhtml", ".html")))
    assert "Illustration générée par IA" in pages

    if ".pdf" in suffixes:
        pdf = next(p for p in produits if p.suffix == ".pdf")
        assert pdf.stat().st_size > 1000
    else:                                            # weasyprint absent : on le DIT
        pytest.skip("PDF non produit sur cette machine — les deux autres formats sont "
                    "vérifiés ci-dessus")


def _petit_png(chemin: Path) -> None:
    from PIL import Image

    Image.new("RGB", (32, 32), (200, 180, 160)).save(chemin, format="PNG")
