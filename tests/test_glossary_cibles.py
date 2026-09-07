# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Alexandre Tournel

"""Glossaire multi-cibles — le seul changement de FORMAT du dépôt.

Trois propriétés, par ordre de gravité si elles cassaient :

1. **La migration ne perd rien, et laisse une sauvegarde.** Un glossaire est du travail humain
   accumulé sur plusieurs tomes ; le convertir est le seul geste irréversible du projet.
2. **Enregistrer dans une cible n'efface pas les autres.** C'est l'invariant qui justifie tout
   le format : sans lui, traduire vers l'anglais détruirait le français.
3. **Le reste du dépôt ne voit rien.** 71 endroits lisent `e["nom"]` : `load` doit rendre la
   forme plate, exactement comme avant.
"""
import yaml

from core import glossary, glossary_cibles


def _ecrire(chemin, données):
    chemin.write_text(yaml.safe_dump(données, allow_unicode=True), encoding="utf-8")


ANCIEN = {
    "personnages": [
        {"nom": "Roi-démon", "pluriel": "Rois-démons", "genre": "masculin",
         "variantes": ["Demon Lord"], "interdits": ["Seigneur démon"],
         "termes_source": ["魔王"], "force": True, "traduire": None,
         "role": "antagoniste", "description": "Souverain du gouffre."},
    ],
    "termes": [{"nom": "Sans-Marque", "termes_source": ["無印"], "traduire": True,
                "description": "Né sans sceau."}],
    "anglicismes": [{"vo": "Yup", "fr": "Ouais"}],
}


# ─────────────────────────────────────────────────────────────────────────────
# 1. La migration
# ─────────────────────────────────────────────────────────────────────────────

def test_la_migration_ne_perd_aucun_champ(tmp_path):
    g = tmp_path / "glossaire.yaml"
    _ecrire(g, ANCIEN)

    plat = glossary.load(g, cible="fr")["personnages"][0]

    for champ, attendu in ANCIEN["personnages"][0].items():
        assert plat[champ] == attendu, champ


def test_la_migration_ecrit_une_sauvegarde_avant_de_reecrire(tmp_path):
    """⚠ Le seul geste irréversible du dépôt. La sauvegarde part AVANT la réécriture."""
    g = tmp_path / "glossaire.yaml"
    _ecrire(g, ANCIEN)
    avant = g.read_text(encoding="utf-8")

    glossary.load(g, cible="fr")

    bak = g.with_suffix(g.suffix + ".avant-multicibles.bak")
    assert bak.exists()
    assert bak.read_text(encoding="utf-8") == avant


def test_une_seconde_migration_necrase_pas_la_sauvegarde(tmp_path):
    """Une `.bak` écrasée par une migration ratée ne servirait à rien."""
    g = tmp_path / "glossaire.yaml"
    _ecrire(g, ANCIEN)
    glossary.load(g, cible="fr")
    bak = g.with_suffix(g.suffix + ".avant-multicibles.bak")
    original = bak.read_text(encoding="utf-8")

    _ecrire(g, {"personnages": [{"nom": "Autre chose"}]})   # re-migrable
    glossary.load(g, cible="fr")

    assert bak.read_text(encoding="utf-8") == original


def test_la_migration_est_idempotente(tmp_path):
    g = tmp_path / "glossaire.yaml"
    _ecrire(g, ANCIEN)
    glossary.load(g, cible="fr")
    apres_une = g.read_text(encoding="utf-8")

    glossary.load(g, cible="fr")

    assert g.read_text(encoding="utf-8") == apres_une


def test_les_champs_de_rendu_descendent_sous_cibles(tmp_path):
    g = tmp_path / "glossaire.yaml"
    _ecrire(g, ANCIEN)
    glossary.load(g, cible="fr")

    e = yaml.safe_load(g.read_text(encoding="utf-8"))["personnages"][0]

    for champ in glossary_cibles.CHAMPS_CIBLE:
        assert champ in e["cibles"]["fr"], champ
        assert champ not in e, champ
    for champ in ("termes_source", "description", "role"):
        assert champ in e, champ


def test_les_categories_sans_entite_ne_sont_pas_migrees(tmp_path):
    """`anglicismes` est un couple `vo → fr`, pas une entité : il n'a pas de rendu par cible."""
    g = tmp_path / "glossaire.yaml"
    _ecrire(g, ANCIEN)
    glossary.load(g, cible="fr")

    brut = yaml.safe_load(g.read_text(encoding="utf-8"))

    assert brut["anglicismes"] == [{"vo": "Yup", "fr": "Ouais"}]


def test_la_migration_range_sous_la_cible_du_run(tmp_path):
    """Un glossaire écrit avant les packs est du français — sauf si l'on traduit déjà vers
    autre chose, auquel cas ces rendus sont ceux de CETTE cible."""
    g = tmp_path / "glossaire.yaml"
    _ecrire(g, ANCIEN)

    glossary.load(g, cible="en")

    e = yaml.safe_load(g.read_text(encoding="utf-8"))["personnages"][0]
    assert "en" in e["cibles"]
    assert "fr" not in e["cibles"]


# ─────────────────────────────────────────────────────────────────────────────
# 2. L'invariant : une cible n'efface pas les autres
# ─────────────────────────────────────────────────────────────────────────────

def test_enregistrer_en_anglais_preserve_le_francais(tmp_path):
    """⚠ L'invariant central. Sans lui, traduire un tome vers l'anglais détruirait le travail
    fait en français, et rien ne le signalerait."""
    g = tmp_path / "glossaire.yaml"
    _ecrire(g, ANCIEN)
    glossary.load(g, cible="fr")

    en = glossary.load(g, cible="en")
    en["personnages"][0]["nom"] = "Demon King"
    glossary.save(en, g, cible="en")

    assert glossary.load(g, cible="fr")["personnages"][0]["nom"] == "Roi-démon"
    assert glossary.load(g, cible="fr")["personnages"][0]["genre"] == "masculin"
    assert glossary.load(g, cible="en")["personnages"][0]["nom"] == "Demon King"


def test_un_reenregistrement_francais_preserve_langlais(tmp_path):
    g = tmp_path / "glossaire.yaml"
    _ecrire(g, ANCIEN)
    en = glossary.load(g, cible="en")
    en["personnages"][0]["nom"] = "Demon King"
    glossary.save(en, g, cible="en")

    fr = glossary.load(g, cible="fr")
    fr["personnages"][0]["description"] = "Mis à jour."
    glossary.save(fr, g, cible="fr")

    assert glossary.load(g, cible="en")["personnages"][0]["nom"] == "Demon King"


def test_les_champs_partages_sont_communs_aux_cibles(tmp_path):
    """`termes_source` est la graphie d'ORIGINE : elle ne dépend pas de la langue de sortie,
    et la dupliquer ferait re-relever le terme au tome suivant."""
    g = tmp_path / "glossaire.yaml"
    _ecrire(g, ANCIEN)
    glossary.load(g, cible="fr")

    assert glossary.load(g, cible="en")["personnages"][0]["termes_source"] == ["魔王"]


def test_une_entite_non_traduite_garde_un_nom_vide(tmp_path):
    """Elle ne DISPARAÎT pas de la vue : le terminologue perdrait la graphie source déjà
    relevée et la re-relèverait au tome suivant."""
    g = tmp_path / "glossaire.yaml"
    _ecrire(g, ANCIEN)
    glossary.load(g, cible="fr")

    en = glossary.load(g, cible="en")["personnages"][0]

    assert en["nom"] == ""
    assert en["termes_source"] == ["魔王"]


def test_un_glossaire_vide_efface_vraiment(tmp_path):
    """La refonte ne doit pas ressusciter depuis le disque ce que l'appelant a supprimé —
    sinon le glossariste ne pourrait jamais dédoublonner."""
    g = tmp_path / "glossaire.yaml"
    _ecrire(g, ANCIEN)
    glossary.load(g, cible="fr")

    glossary.save(glossary.empty(), g, cible="fr")

    assert glossary.load(g, cible="fr").get("personnages") in (None, [])


def test_lappariement_se_fait_par_terme_source(tmp_path):
    """Deux cibles n'ont pas le même `nom` pour la même entité : s'apparier uniquement par
    `nom` créerait un doublon par langue."""
    g = tmp_path / "glossaire.yaml"
    _ecrire(g, ANCIEN)
    glossary.load(g, cible="fr")

    en = glossary.load(g, cible="en")
    en["personnages"][0]["nom"] = "Demon King"
    glossary.save(en, g, cible="en")

    brut = yaml.safe_load(g.read_text(encoding="utf-8"))
    assert len(brut["personnages"]) == 1, "une entité, pas deux"
    assert set(brut["personnages"][0]["cibles"]) == {"fr", "en"}


def test_cibles_presentes(tmp_path):
    g = tmp_path / "glossaire.yaml"
    _ecrire(g, ANCIEN)
    glossary.load(g, cible="fr")
    en = glossary.load(g, cible="en")
    en["personnages"][0]["nom"] = "Demon King"
    glossary.save(en, g, cible="en")

    brut = yaml.safe_load(g.read_text(encoding="utf-8"))

    assert glossary_cibles.cibles_presentes(brut) == ["en", "fr"]


# ─────────────────────────────────────────────────────────────────────────────
# 3. Le reste du dépôt ne voit rien
# ─────────────────────────────────────────────────────────────────────────────

def test_la_vue_est_plate_comme_avant(tmp_path):
    """71 endroits lisent `e["nom"]`, `e["genre"]`… : aucun ne doit connaître `cibles`."""
    g = tmp_path / "glossaire.yaml"
    _ecrire(g, ANCIEN)

    e = glossary.load(g, cible="fr")["personnages"][0]

    assert glossary_cibles.CLE_CIBLES not in e
    assert e["nom"] == "Roi-démon" and e["genre"] == "masculin"


def test_un_aller_retour_plat_ne_change_rien(tmp_path):
    """⚠ L'idempotence se mesure à partir du SECOND tour, pas du premier : `save` passe par
    `fill_defaults`, qui ajoute les champs vides que le fichier doit afficher (« chaque entrée
    affiche tous ses champs — complète-les librement », dit son en-tête). Le premier
    enregistrement en ajoute donc, légitimement ; les suivants ne doivent plus rien changer."""
    g = tmp_path / "glossaire.yaml"
    _ecrire(g, ANCIEN)
    glossary.load(g, cible="fr")

    glossary.save(glossary.load(g, cible="fr"), g, cible="fr")
    stable = glossary.load(g, cible="fr")
    glossary.save(stable, g, cible="fr")

    assert glossary.load(g, cible="fr") == stable


def test_un_aller_retour_ne_perd_aucun_champ_dorigine(tmp_path):
    g = tmp_path / "glossaire.yaml"
    _ecrire(g, ANCIEN)
    glossary.save(glossary.load(g, cible="fr"), g, cible="fr")

    e = glossary.load(g, cible="fr")["personnages"][0]

    for champ, attendu in ANCIEN["personnages"][0].items():
        assert e[champ] == attendu, champ


def test_la_cible_du_run_sert_de_defaut(tmp_path):
    g = tmp_path / "glossaire.yaml"
    _ecrire(g, ANCIEN)
    glossary.load(g, cible="fr")
    precedente = glossary.cible_du_run()
    try:
        glossary.definir_cible("en")
        assert glossary.load(g)["personnages"][0]["nom"] == ""
        glossary.definir_cible("fr")
        assert glossary.load(g)["personnages"][0]["nom"] == "Roi-démon"
    finally:
        glossary.definir_cible(precedente)


# ─────────────────────────────────────────────────────────────────────────────
# 4. L'accord grammatical est une FONCTION du pack
# ─────────────────────────────────────────────────────────────────────────────

def _glo_force(nom, **champs):
    from core import glossary as g
    base = g.empty()
    base["termes"] = [{"nom": nom, "force": True, **champs}]
    return base


def test_le_francais_repare_lelision():
    """Le comportement d'avant les packs, inchangé : « l'infirmière » → « la médecin de
    combat » et non « l'médecin de combat »."""
    from core.glossary_force import AccordFrancais, enforce_force

    glo = _glo_force("médecin de combat", genre="féminin", interdits=["infirmière"])
    texte, n = enforce_force("Elle vit l'infirmière partir.", glo, accord=AccordFrancais())

    assert n == 1
    assert "la médecin de combat" in texte
    assert "l'médecin" not in texte


def test_le_francais_refuse_plutot_que_de_fauter():
    """⚠ Le principe à préserver quelle que soit la langue : le déterministe ne doit JAMAIS
    introduire une faute que le modèle n'aurait pas faite."""
    from core.glossary_force import AccordFrancais, enforce_force

    glo = _glo_force("médecin de combat", genre="?", interdits=["infirmière"])
    refus = []
    texte, n = enforce_force("Elle vit l'infirmière partir.", glo, refus,
                             accord=AccordFrancais())

    assert n == 0
    assert "infirmière" in texte
    assert refus and "genre inconnu" in refus[0]


def test_laccord_neutre_substitue_sans_toucher_au_determinant():
    """L'anglais n'a ni genre, ni élision, ni déterminant à réécrire : « ne rien faire » est
    la réponse complète, pas une implémentation en attente."""
    from core.glossary_force import AccordNeutre, enforce_force

    glo = _glo_force("Demon King", interdits=["Demon Lord"])
    texte, n = enforce_force("She saw the Demon Lord leave.", glo, accord=AccordNeutre())

    assert n == 1
    assert texte == "She saw the Demon King leave."


def test_laccord_neutre_ne_refuse_jamais_pour_un_genre():
    """Refuser faute de genre n'aurait aucun sens dans une langue qui n'en a pas."""
    from core.glossary_force import AccordNeutre, enforce_force

    glo = _glo_force("Demon King", genre="?", interdits=["Demon Lord"])
    refus = []
    _texte, n = enforce_force("the Demon Lord", glo, refus, accord=AccordNeutre())

    assert n == 1
    assert refus == []


def test_le_defaut_reste_le_francais():
    """Sans pack, le comportement ne change pas — c'est ce qui rend la refonte sûre."""
    from core.glossary_force import AccordFrancais, ACCORD_DEFAUT, enforce_force

    assert isinstance(ACCORD_DEFAUT, AccordFrancais)

    glo = _glo_force("médecin de combat", genre="féminin", interdits=["infirmière"])
    sans, _ = enforce_force("Elle vit l'infirmière.", glo)
    avec, _ = enforce_force("Elle vit l'infirmière.", glo, accord=AccordFrancais())

    assert sans == avec


def test_chaque_pack_livre_declare_un_accord_connu():
    """Un `accord:` mal orthographié retomberait sur le français en silence — donc des
    élisions françaises réécrites au milieu d'un texte anglais."""
    from pathlib import Path

    from core import langues
    from core.glossary_force import ACCORDS

    racine = Path(__file__).resolve().parent.parent
    for dossier in sorted((racine / "langues").iterdir()):
        if not (dossier / "pack.yaml").exists():
            continue
        meta = yaml.safe_load((dossier / "pack.yaml").read_text(encoding="utf-8"))
        assert meta.get("accord") in ACCORDS, f"{dossier.name} : {meta.get('accord')!r}"
        pack = langues.resoudre_pack(
            {"langues": {"cible": dossier.name, "packs": str(racine / "langues")}})
        assert pack.accorder() is not None
