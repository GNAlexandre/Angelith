# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Alexandre Tournel

"""Résolution du pack de langue cible.

Deux propriétés dominent tout le reste de ce fichier :

1. **Le mode compatibilité rend EXACTEMENT les chemins d'avant.** C'est ce qui fait de la
   refonte un MINEUR : une config qui ne mentionne pas `langues.cible`, sur un dépôt sans
   dossier `langues/`, doit produire la même sortie au bit près.
2. **Aucun repli silencieux.** Un pack demandé mais introuvable ou incomplet arrête le
   programme au démarrage. Six heures de GPU pour découvrir qu'un tome est sorti dans la
   mauvaise langue coûtent bien plus cher qu'un refus immédiat.
"""
import pytest

from core import langues


def _pack_sur_disque(racine, code, *, prompts=None, pack_yaml="code: {code}\n", **fichiers):
    """Fabrique un pack minimal mais VALIDE. `prompts=None` = les huit requis."""
    dossier = racine / code
    (dossier / "prompts").mkdir(parents=True)
    if pack_yaml is not None:
        (dossier / "pack.yaml").write_text(pack_yaml.format(code=code), encoding="utf-8")
    for nom in (langues.PROMPTS_REQUIS if prompts is None else prompts):
        (dossier / "prompts" / f"{nom}.md").write_text(f"# {nom}\n", encoding="utf-8")
    for relatif, contenu in fichiers.items():
        chemin = dossier / relatif.replace("__", "/")
        chemin.parent.mkdir(parents=True, exist_ok=True)
        chemin.write_text(contenu, encoding="utf-8")
    return dossier


CONFIG_HISTORIQUE = {
    "chemins": {"prompts": "prompts", "style_guide": "style_guide.md"},
    "rendu": {"reference_docx": "templates/reference.docx", "epub_css": "templates/epub.css"},
}


# ─────────────────────────────────────────────────────────────────────────────
# Mode compatibilité
# ─────────────────────────────────────────────────────────────────────────────

def test_sans_dossier_langues_on_lit_les_anciens_emplacements(tmp_path, monkeypatch):
    """La propriété qui fait de cette refonte un MINEUR."""
    monkeypatch.chdir(tmp_path)

    pack = langues.resoudre_pack(CONFIG_HISTORIQUE)

    assert pack.racine is None
    assert pack.code == "fr"
    assert pack.prompt("traducteur").as_posix() == "prompts/traducteur.md"
    # ⚠ `fichier()` rend `None` : sans pack, le socle n'a RIEN à dire sur le guide de style
    # ni sur les gabarits — ce sont des artefacts du light novel, et c'est la brique qui
    # retombe sur sa propre config (cf. `Pack.fichier`).
    assert pack.fichier("style_guide.md") is None
    assert pack.fichier("templates/reference.docx") is None


def test_une_config_vide_reste_en_francais(tmp_path, monkeypatch):
    """Aucune clé `langues` du tout : c'est la config d'un utilisateur qui met à jour sans
    rien toucher."""
    monkeypatch.chdir(tmp_path)

    pack = langues.resoudre_pack({})

    assert pack.racine is None
    assert pack.nom_lisible() == "français"


def test_cible_fr_explicite_vaut_le_defaut(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    assert langues.resoudre_pack({"langues": {"cible": "fr"}}).racine is None


def test_les_chemins_de_repli_suivent_la_config(tmp_path, monkeypatch):
    """Un utilisateur qui a déplacé ses prompts doit garder ses prompts.

    `chemins.prompts` est la SEULE clé de chemin que le socle connaisse : c'est la seule que
    les deux briques partagent (cf. la docstring de `manga/agents_manga.py`)."""
    monkeypatch.chdir(tmp_path)

    pack = langues.resoudre_pack({"chemins": {"prompts": "mes_prompts"}})

    assert pack.prompt("correcteur").as_posix() == "mes_prompts/correcteur.md"


# ─────────────────────────────────────────────────────────────────────────────
# Pack réel
# ─────────────────────────────────────────────────────────────────────────────

def test_un_pack_present_prend_le_pas(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _pack_sur_disque(tmp_path / "langues", "en", pack_yaml="code: en\nnom: English\n")

    pack = langues.resoudre_pack({"langues": {"cible": "en"}, **CONFIG_HISTORIQUE})

    assert pack.code == "en"
    assert pack.nom_lisible() == "English"
    assert pack.prompt("traducteur").as_posix().endswith("langues/en/prompts/traducteur.md")


def test_le_nom_lisible_retombe_sur_la_table_des_langues(tmp_path, monkeypatch):
    """`glossary_lang.NOMS` existe déjà et sert la langue source ; un pack qui ne déclare pas
    son nom doit en profiter plutôt que d'afficher un code ISO à un modèle."""
    monkeypatch.chdir(tmp_path)
    _pack_sur_disque(tmp_path / "langues", "de", pack_yaml="code: de\n")

    assert langues.resoudre_pack({"langues": {"cible": "de"}}).nom_lisible() == "allemand"


def test_racine_de_packs_personnalisee(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _pack_sur_disque(tmp_path / "mes_langues", "en")

    pack = langues.resoudre_pack({"langues": {"cible": "en", "packs": "mes_langues"}})

    assert pack.racine.as_posix().endswith("mes_langues/en")


def test_les_gabarits_absents_retombent_sur_la_config(tmp_path, monkeypatch):
    """Volontairement tolérant, contrairement aux prompts : un `reference.docx` est déjà un
    réglage que l'utilisateur personnalise, et un pack qui n'en fournit pas n'est pas cassé."""
    monkeypatch.chdir(tmp_path)
    _pack_sur_disque(tmp_path / "langues", "en")

    pack = langues.resoudre_pack({"langues": {"cible": "en"}, **CONFIG_HISTORIQUE})

    # Le pack n'en fournit pas : `None`, donc la brique garde son `rendu.reference_docx`.
    assert pack.fichier("templates/reference.docx") is None
    assert pack.fichier("templates/epub.css") is None


def test_les_gabarits_du_pack_priment(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _pack_sur_disque(tmp_path / "langues", "en",
                     templates__epub__css="p{}", templates__reference__docx="x")
    # Le nom réel porte un point, que le raccourci `__` ne sait pas écrire.
    d = tmp_path / "langues" / "en" / "templates"
    (d / "epub.css").write_text("p{}", encoding="utf-8")
    (d / "reference.docx").write_text("x", encoding="utf-8")

    pack = langues.resoudre_pack({"langues": {"cible": "en"}, **CONFIG_HISTORIQUE})

    assert pack.fichier("templates/epub.css").as_posix().endswith(
        "langues/en/templates/epub.css")
    assert pack.fichier("templates/reference.docx").as_posix().endswith(
        "langues/en/templates/reference.docx")


# ─────────────────────────────────────────────────────────────────────────────
# Refus — la règle « aucun repli silencieux »
# ─────────────────────────────────────────────────────────────────────────────

def test_pack_introuvable_arrete_et_liste_les_packs(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _pack_sur_disque(tmp_path / "langues", "fr")
    _pack_sur_disque(tmp_path / "langues", "en")

    with pytest.raises(SystemExit) as err:
        langues.resoudre_pack({"langues": {"cible": "de"}})

    message = str(err.value)
    assert "de" in message
    assert "en, fr" in message, message


def test_une_faute_de_frappe_est_nommee(tmp_path, monkeypatch):
    """Même geste que `core.config._suggestion` : `cible: fp` est une faute de frappe bien
    plus probable qu'une demande de pack finnois."""
    monkeypatch.chdir(tmp_path)
    _pack_sur_disque(tmp_path / "langues", "fr")

    with pytest.raises(SystemExit) as err:
        langues.resoudre_pack({"langues": {"cible": "fp"}})

    assert "vouliez-vous dire « fr »" in str(err.value)


def test_cible_non_defaut_sans_dossier_langues_refuse(tmp_path, monkeypatch):
    """Le repli de compatibilité ne vaut QUE pour le français. Demander l'allemand sans pack
    doit échouer, pas produire du français en silence."""
    monkeypatch.chdir(tmp_path)

    with pytest.raises(SystemExit):
        langues.resoudre_pack({"langues": {"cible": "de"}})


def test_pack_ampute_dun_prompt_refuse_en_le_nommant(tmp_path, monkeypatch):
    """Servir le prompt français d'un agent absent produirait un tome dont les onomatopées
    seraient françaises et le reste anglais."""
    monkeypatch.chdir(tmp_path)
    partiels = [n for n in langues.PROMPTS_REQUIS if n != "manga_onomatopees"]
    _pack_sur_disque(tmp_path / "langues", "en", prompts=partiels)

    with pytest.raises(SystemExit) as err:
        langues.resoudre_pack({"langues": {"cible": "en"}})

    assert "manga_onomatopees.md" in str(err.value)


def test_pack_sans_pack_yaml_refuse(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _pack_sur_disque(tmp_path / "langues", "en", pack_yaml=None)

    with pytest.raises(SystemExit) as err:
        langues.resoudre_pack({"langues": {"cible": "en"}})

    assert "pack.yaml" in str(err.value)


def test_pack_yaml_illisible_refuse(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _pack_sur_disque(tmp_path / "langues", "en", pack_yaml="code: [en\n")

    with pytest.raises(SystemExit) as err:
        langues.resoudre_pack({"langues": {"cible": "en"}})

    assert "illisible" in str(err.value)


# ─────────────────────────────────────────────────────────────────────────────
# Consignes
# ─────────────────────────────────────────────────────────────────────────────

def test_une_consigne_non_declaree_rend_le_defaut(tmp_path, monkeypatch):
    """⚠ Le défaut est le texte français, et il vit à son SITE D'APPEL. Le recopier dans le
    pack `fr` en ferait une seconde source libre de diverger, dont l'une déciderait de la
    sortie d'un tome."""
    monkeypatch.chdir(tmp_path)

    pack = langues.resoudre_pack({})

    assert pack.consigne("titre_chapitre", "TEXTE D'ORIGINE") == "TEXTE D'ORIGINE"


def test_un_pack_peut_surcharger_une_consigne(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _pack_sur_disque(tmp_path / "langues", "en",
                     pack_yaml="code: en\nconsignes:\n  titre_chapitre: Translate the title.\n")

    pack = langues.resoudre_pack({"langues": {"cible": "en"}})

    assert pack.consigne("titre_chapitre", "TEXTE D'ORIGINE") == "Translate the title."
    assert pack.consigne("traduction_unitaire", "AUTRE") == "AUTRE"


def test_une_consigne_vide_ne_masque_pas_le_defaut(tmp_path, monkeypatch):
    """Une clé laissée vide dans le YAML donne `None` ou `""` : la traiter comme une
    surcharge enverrait une consigne VIDE au modèle, ce qui est pire que le français."""
    monkeypatch.chdir(tmp_path)
    _pack_sur_disque(tmp_path / "langues", "en",
                     pack_yaml="code: en\nconsignes:\n  titre_chapitre:\n")

    pack = langues.resoudre_pack({"langues": {"cible": "en"}})

    assert pack.consigne("titre_chapitre", "DEFAUT") == "DEFAUT"


def test_toutes_les_cles_de_consigne_utilisees_sont_declarees():
    """`CONSIGNES_CONNUES` sert de référence à `langues/README.md` : une clé employée par le
    code mais absente de la liste ne serait documentée nulle part.

    ⚠ Depuis le lot 15, la table de `manga/consignes.py` est confrontée EN ENTIER à la liste
    du socle. C'est ce qui empêche la dérive que l'externalisation elle-même rend possible :
    ajouter un fragment côté brique sans le déclarer côté socle donnerait une consigne qu'un
    pack ne peut pas surcharger — c'est-à-dire un retour silencieux au français en dur —
    exactement ce que le lot corrige."""
    from manga import consignes, relecture, traduction_unitaire

    assert traduction_unitaire.CLE_CONSIGNE in langues.CONSIGNES_CONNUES
    assert relecture.CLE_CONSIGNE in langues.CONSIGNES_CONNUES
    for cle in ("naturalisation_minimale", "naturalisation_legere", "naturalisation_moderee",
                "naturalisation_marquee", "titre_chapitre", "romanisation_rendu"):
        assert cle in langues.CONSIGNES_CONNUES

    non_declarees = [c for c in consignes.CLES if c not in langues.CONSIGNES_CONNUES]
    assert non_declarees == [], (
        "fragments du chemin manga employés par le code mais absents de "
        f"core.langues.CONSIGNES_CONNUES : {non_declarees}")
