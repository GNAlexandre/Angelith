# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Alexandre Tournel

"""Réintégration d'un glossaire YAML antérieur (`--migrate-glossary`).

La 2.0.0 a livré une migration automatique, mais elle n'a qu'un déclencheur :
`glossary.load` sur `sources/<Projet>/glossaire.yaml`. Un ancien glossaire rangé
ailleurs — un `.bak`, un export, une copie d'une installation précédente, le glossaire
d'une œuvre sœur — n'est lu par personne et reste donc perdu.

Quatre propriétés, par ordre de gravité si elles cassaient :

1. **La source n'est jamais modifiée.** On vient récupérer un fichier de sauvegarde ; le
   réécrire (ce que fait `glossary.load`) détruirait le filet qu'on est venu chercher.
2. **Rien n'est perdu.** Ni les entrées de l'ancien fichier, ni celles du glossaire en
   place, ni les rendus des AUTRES langues cibles.
3. **Le fichier réintégré fait autorité.** Sinon le glossaire en place — souvent celui
   qu'on cherche justement à réparer — écraserait le travail à restaurer.
4. **L'existant part en sauvegarde avant d'être remplacé**, et une seconde exécution ne
   l'écrase pas.
"""
import hashlib

import pytest
import yaml

from core import glossary, glossary_cibles, glossary_import as gi


def _config(tmp_path):
    return {"chemins": {"sources": str(tmp_path / "sources"), "glossaire_fichier": "glossaire.yaml"}}


def _projet(tmp_path, nom="Projet"):
    d = tmp_path / "sources" / nom
    d.mkdir(parents=True, exist_ok=True)
    return d


def _ecrire(chemin, donnees):
    chemin.write_text(yaml.safe_dump(donnees, allow_unicode=True), encoding="utf-8")
    return chemin


def _md5(chemin):
    return hashlib.md5(chemin.read_bytes()).hexdigest()


#: Glossaire à l'ANCIEN format (plat, un seul emplacement de rendu, sans langue).
ANCIEN = {
    "personnages": [
        {"nom": "Feodor Jessman", "pluriel": "", "genre": "masculin",
         "variantes": ["Féodor"], "termes_source": ["フェオドール"], "interdits": [],
         "role": "protagoniste", "description": "Quatrième officier.", "force": False},
    ],
    "creatures": [
        {"nom": "Leprechaun", "genre": "?", "traduire": None, "variantes": [],
         "termes_source": ["黄金妖精レプラカーン"], "interdits": ["lutin"],
         "description": "Fées dorées.", "force": True},
    ],
    "anglicismes": [{"vo": "Yup", "fr": "Ouais"}],
}


# ─────────────────────────────────────────────────────────────────────────────
# 1. La source n'est jamais modifiée
# ─────────────────────────────────────────────────────────────────────────────

def test_le_fichier_reintegre_reste_intact_bit_pour_bit(tmp_path):
    """⚠ La propriété la plus grave. `glossary.load` migre ET RÉÉCRIT le fichier qu'il
    ouvre : l'appliquer à un `.bak` détruirait la sauvegarde qu'on vient restaurer."""
    _projet(tmp_path)
    src = _ecrire(tmp_path / "ancien.bak.yaml", ANCIEN)
    avant = _md5(src)

    gi.reintegrer_dans_projet("Projet", [src], _config(tmp_path))

    assert _md5(src) == avant


def test_lire_glossaire_yaml_migre_en_memoire_sans_toucher_au_disque(tmp_path):
    src = _ecrire(tmp_path / "ancien.yaml", ANCIEN)
    avant = _md5(src)

    plat, etait_ancien, migrees = gi.lire_glossaire_yaml(src, "fr")

    assert (etait_ancien, migrees) == (True, 2)          # 2 entités ; l'anglicisme ne migre pas
    assert plat["personnages"][0]["nom"] == "Feodor Jessman"   # vue PLATE, comme `glossary.load`
    assert _md5(src) == avant


def test_lire_glossaire_yaml_refuse_un_chemin_inexistant(tmp_path):
    with pytest.raises(RuntimeError, match="introuvable"):
        gi.lire_glossaire_yaml(tmp_path / "nulle-part.yaml", "fr")


# ─────────────────────────────────────────────────────────────────────────────
# 2. Rien n'est perdu
# ─────────────────────────────────────────────────────────────────────────────

def test_un_ancien_glossaire_est_converti_sans_perdre_un_champ(tmp_path):
    _projet(tmp_path)
    src = _ecrire(tmp_path / "ancien.yaml", ANCIEN)

    gpath, total, _ = gi.reintegrer_dans_projet("Projet", [src], _config(tmp_path))

    brut = yaml.safe_load(gpath.read_text(encoding="utf-8"))
    assert not glossary_cibles.besoin_de_migration(brut)
    assert glossary_cibles.cibles_presentes(brut) == ["fr"]

    relu = glossary.load(gpath)
    for cat in ("personnages", "creatures"):
        attendu, obtenu = ANCIEN[cat][0], relu[cat][0]
        for champ, valeur in attendu.items():
            assert obtenu[champ] == valeur, f"{cat}.{champ}"
    assert relu["anglicismes"] == ANCIEN["anglicismes"]     # jamais migré, jamais perdu
    assert total["entrees"] == 3


def test_le_glossaire_en_place_est_fusionne_en_dernier_pas_ecrase(tmp_path):
    d = _projet(tmp_path)
    glossary.save({"personnages": [{"nom": "Tiat Siba Ignareo", "genre": "féminin",
                                    "termes_source": ["ティアット"]}]},
                  d / "glossaire.yaml", cible="fr")
    src = _ecrire(tmp_path / "ancien.yaml", ANCIEN)

    gpath, _, _ = gi.reintegrer_dans_projet("Projet", [src], _config(tmp_path))

    noms = {p["nom"] for p in glossary.load(gpath)["personnages"]}
    assert noms == {"Feodor Jessman", "Tiat Siba Ignareo"}


def test_les_rendus_des_autres_langues_survivent(tmp_path):
    """L'invariant central du format multi-cibles : réintégrer du français ne doit pas
    effacer l'anglais déjà écrit pour la même entité."""
    d = _projet(tmp_path)
    _ecrire(d / "glossaire.yaml", {"creatures": [
        {"termes_source": ["黄金妖精レプラカーン"], "description": "Fées dorées.",
         "cibles": {"en": {"nom": "Leprechaun", "genre": "?", "variantes": ["golden fairy"],
                           "interdits": [], "pluriel": "", "force": True}}},
    ]})
    src = _ecrire(tmp_path / "ancien.yaml", ANCIEN)

    gpath, _, _ = gi.reintegrer_dans_projet("Projet", [src], _config(tmp_path))

    brut = yaml.safe_load(gpath.read_text(encoding="utf-8"))
    assert set(glossary_cibles.cibles_presentes(brut)) == {"fr", "en"}
    (entree,) = brut["creatures"]
    assert entree["cibles"]["en"]["variantes"] == ["golden fairy"]
    assert entree["cibles"]["fr"]["nom"] == "Leprechaun"
    # Une entrée sans rendu dans la cible courante a un `nom` VIDE : elle ne doit pas
    # devenir une variante vide au passage.
    assert "" not in (entree["cibles"]["fr"]["variantes"] or [])


def test_plusieurs_fichiers_sont_fusionnes_dans_l_ordre_donne(tmp_path):
    _projet(tmp_path)
    a = _ecrire(tmp_path / "a.yaml", ANCIEN)
    b = _ecrire(tmp_path / "b.yaml", {"personnages": [
        {"nom": "Feodor Jessman", "termes_source": ["フェオドール", "フェオ"],
         "variantes": ["Fwedo"], "genre": "masculin", "description": "Autre fiche."},
        {"nom": "Nax Selzel", "genre": "masculin", "termes_source": ["ナックス"]},
    ]})

    gpath, total, rapport = gi.reintegrer_dans_projet("Projet", [a, b], _config(tmp_path))

    relu = glossary.load(gpath)
    feodor = next(p for p in relu["personnages"] if p["nom"] == "Feodor Jessman")
    # Union sur les listes, mais la description du PREMIER fichier tient.
    assert set(feodor["termes_source"]) == {"フェオドール", "フェオ"}
    assert set(feodor["variantes"]) >= {"Féodor", "Fwedo"}
    assert feodor["description"] == "Quatrième officier."
    assert any(p["nom"] == "Nax Selzel" for p in relu["personnages"])
    assert len(rapport) == 2 and total["conflits"] == 0


# ─────────────────────────────────────────────────────────────────────────────
# 3. Le fichier réintégré fait autorité
# ─────────────────────────────────────────────────────────────────────────────

def test_le_fichier_reintegre_prime_sur_le_glossaire_en_place(tmp_path):
    """Le cas roman N : le fichier en place porte une romanisation dégradée de la même
    entité (même graphie source). C'est l'ancien glossaire qui doit gagner."""
    d = _projet(tmp_path)
    glossary.save({"personnages": [{"nom": "Feodoro", "genre": "?",
                                    "termes_source": ["フェオドール"],
                                    "description": "Relevé brut."}]},
                  d / "glossaire.yaml", cible="fr")
    src = _ecrire(tmp_path / "ancien.yaml", ANCIEN)

    gpath, _, _ = gi.reintegrer_dans_projet("Projet", [src], _config(tmp_path))

    (feodor,) = glossary.load(gpath)["personnages"]         # dédoublonné par termes_source
    assert feodor["nom"] == "Feodor Jessman"
    assert feodor["genre"] == "masculin"
    assert feodor["description"] == "Quatrième officier."
    assert "Feodoro" in feodor["variantes"]                 # la forme vue n'est pas jetée


# ─────────────────────────────────────────────────────────────────────────────
# 4. Sauvegarde, remplacement, dry-run
# ─────────────────────────────────────────────────────────────────────────────

def test_remplacer_ignore_l_existant_mais_le_sauvegarde(tmp_path):
    d = _projet(tmp_path)
    glossary.save({"personnages": [{"nom": "Feodoro", "termes_source": ["フェオドール"]}]},
                  d / "glossaire.yaml", cible="fr")
    avant = (d / "glossaire.yaml").read_text(encoding="utf-8")
    src = _ecrire(tmp_path / "ancien.yaml", ANCIEN)

    gpath, total, rapport = gi.reintegrer_dans_projet(
        "Projet", [src], _config(tmp_path), remplacer=True)

    sauvegarde = gpath.with_suffix(gpath.suffix + gi.SUFFIXE_SAUVEGARDE)
    assert sauvegarde.read_text(encoding="utf-8") == avant
    assert total["sauvegarde"] == sauvegarde
    assert len(rapport) == 1                                # l'existant n'a pas été lu
    (feodor,) = glossary.load(gpath)["personnages"]
    assert feodor["nom"] == "Feodor Jessman" and "Feodoro" not in (feodor["variantes"] or [])


def test_une_seconde_reintegration_n_ecrase_pas_la_sauvegarde(tmp_path):
    """Sans cette garde, la 2e exécution remplacerait la sauvegarde par le résultat de la
    1re, et l'état d'origine serait définitivement perdu."""
    d = _projet(tmp_path)
    glossary.save({"personnages": [{"nom": "Feodoro", "termes_source": ["フェオドール"]}]},
                  d / "glossaire.yaml", cible="fr")
    origine = (d / "glossaire.yaml").read_text(encoding="utf-8")
    src = _ecrire(tmp_path / "ancien.yaml", ANCIEN)
    cfg = _config(tmp_path)

    gi.reintegrer_dans_projet("Projet", [src], cfg, remplacer=True)
    gi.reintegrer_dans_projet("Projet", [src], cfg, remplacer=True)

    sauvegarde = d / ("glossaire.yaml" + gi.SUFFIXE_SAUVEGARDE)
    assert sauvegarde.read_text(encoding="utf-8") == origine


def test_migrer_un_glossaire_sur_place_ne_le_fusionne_pas_avec_lui_meme(tmp_path):
    """`--migrate-glossary sources/X/glossaire.yaml` : le fichier est sa propre source.
    Le lire ET le fusionner en tant qu'« existant » doublerait le rapport."""
    d = _projet(tmp_path)
    gpath_src = _ecrire(d / "glossaire.yaml", ANCIEN)

    gpath, total, rapport = gi.reintegrer_dans_projet("Projet", [gpath_src], _config(tmp_path))

    assert len(rapport) == 1 and total["entrees"] == 3
    brut = yaml.safe_load(gpath.read_text(encoding="utf-8"))
    assert not glossary_cibles.besoin_de_migration(brut)
    assert (d / ("glossaire.yaml" + gi.SUFFIXE_SAUVEGARDE)).exists()


def test_dry_run_n_ecrit_rien(tmp_path):
    d = _projet(tmp_path)
    src = _ecrire(tmp_path / "ancien.yaml", ANCIEN)

    gpath, total, rapport = gi.reintegrer_dans_projet(
        "Projet", [src], _config(tmp_path), dry_run=True)

    assert total["entrees"] == 3 and rapport            # le rapport est bien calculé…
    assert not gpath.exists()                           # …mais rien n'est écrit
    assert not list(d.iterdir())


# ─────────────────────────────────────────────────────────────────────────────
# 5. Les deux portes d'entrée de la fusion ne doivent pas diverger
# ─────────────────────────────────────────────────────────────────────────────

def test_fusionner_glossaire_donne_le_meme_resultat_que_merge_notes(tmp_path):
    """`merge_notes` (texte du terminologue) et `fusionner_glossaire` (dict d'un ancien
    fichier) partagent le même corps : les laisser diverger ferait dédoublonner
    différemment selon la porte d'entrée."""
    from core import glossary_build

    notes = "### PERSONNAGES\n- Feodor Jessman | genre: masculin | variantes: Féodor | Officier."
    par_texte = glossary.empty()
    glossary_build.merge_notes(par_texte, notes)
    par_dict = glossary.empty()
    glossary_build.fusionner_glossaire(par_dict, glossary_build.parse_notes(notes))

    assert par_texte == par_dict
