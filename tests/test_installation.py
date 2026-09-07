# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Alexandre Tournel

"""`core/installation.py` — les trois racines, et **le critère 3 du dépôt avant tout**.

## Ce que ce fichier protège

Le critère 3 de la définition de « terminé » : « le comportement livré par défaut est **iso**
pour un utilisateur qui ne touche à rien ». Le lot 37 déplace `config.yaml` et `.angelith/`
dans une **installation gelée** — et dans le dépôt, rien ne doit bouger. C'est une propriété
qui s'affirme facilement et se perd sans bruit : la première moitié de ce fichier ne teste donc
que ça, en assertant que chaque fonction rend l'ancien résultat quand `gele()` est faux.

La seconde moitié tient les trois pièges du `PLAN-37` L37.4 :

1. le premier lancement **copie** le `config.yaml` livré, et **ne le remplace jamais** ensuite ;
2. l'écart de version avec le fichier livré est **dit**, jamais fusionné ;
3. `chemins.sources` et `chemins.build` ne pointent pas dans le dossier d'installation.

⚠ **Le gel se simule, il ne se construit pas.** `monkeypatch.setattr(sys, "frozen", True)` et
un `_MEIPASS` sur un `tmp_path` reproduisent exactement ce que `gele()` lit. Construire un vrai
`.exe` pour un test unitaire coûterait plusieurs minutes par exécution ; la CI, elle, le fait —
une fois, sur le vrai binaire (`PLAN-37` L37.7).
"""
from __future__ import annotations

import hashlib
import sys
from pathlib import Path

import pytest
import yaml

from core import installation as ins

RACINE = Path(__file__).resolve().parent.parent


@pytest.fixture
def gel(monkeypatch, tmp_path):
    """Un faux gel : `sys.frozen`, un `_MEIPASS`, et les deux racines dans `tmp_path`."""
    livree = tmp_path / "installation"
    livree.mkdir()
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "_MEIPASS", str(livree), raising=False)
    monkeypatch.setenv(ins.VAR_DONNEES, str(tmp_path / "donnees"))
    monkeypatch.setenv(ins.VAR_DOCUMENTS, str(tmp_path / "documents"))
    return livree


# --------------------------------------------------------------------------- #
#  Le critère 3 — rien ne bouge dans le dépôt
# --------------------------------------------------------------------------- #

def test_hors_gel_rien_n_est_gele():
    assert ins.gele() is False


def test_hors_gel_la_racine_livree_est_la_racine_du_depot():
    assert ins.racine_livree() == RACINE
    assert ins.ressource("config.yaml") == RACINE / "config.yaml"
    assert ins.ressource("config.yaml").is_file()


def test_hors_gel_resoudre_config_rend_l_argument_tel_quel():
    """⚠ `Path("config.yaml")` RELATIF, et pas un absolu : deux copies du dépôt sur la même
    machine doivent lire chacune la sienne, comme avant le lot."""
    assert ins.resoudre_config(None) == Path("config.yaml")
    assert ins.resoudre_config("config.yaml") == Path("config.yaml")
    assert ins.resoudre_config("autre.yaml") == Path("autre.yaml")


def test_hors_gel_ancrer_chemins_ne_change_rien():
    config = {"chemins": {"sources": "sources", "build": "build"},
              "manga": {"detection": {"model_path": "manga_models/bubble_detector.onnx"}}}
    avant = yaml.safe_dump(config, sort_keys=True)
    ins.ancrer_chemins(config)
    assert yaml.safe_dump(config, sort_keys=True) == avant


def test_hors_gel_le_dossier_de_reglages_est_le_repertoire_courant():
    assert ins.dossier_reglages() == Path.cwd()


def test_hors_gel_donnee_livree_ne_replie_pas(monkeypatch, tmp_path):
    """La propriété que `tests/test_langues_pack.py` a fait tomber le 2026-09-06.

    Depuis un répertoire courant vide, `donnee_livree("langues")` doit rendre `langues` — le
    chemin relatif inexistant — et non le `langues/` du dépôt. Sinon le mode COMPATIBILITÉ de
    `core/langues.py` ne se déclenche plus jamais."""
    monkeypatch.chdir(tmp_path)
    assert ins.donnee_livree("langues") == Path("langues")


# --------------------------------------------------------------------------- #
#  En gel — les trois racines
# --------------------------------------------------------------------------- #

def test_en_gel_la_racine_livree_est_meipass(gel):
    assert ins.gele() is True
    assert ins.racine_livree() == gel
    assert ins.ressource("langues", "fr") == gel / "langues" / "fr"


def test_en_gel_les_trois_racines_sont_distinctes(gel):
    assert len({ins.racine_livree(), ins.dossier_utilisateur(),
                ins.dossier_documents()}) == 3


def test_en_gel_donnee_livree_replie_sur_le_paquet(gel, monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    (gel / "langues").mkdir()
    assert ins.donnee_livree("langues") == gel / "langues"


def test_en_gel_donnee_livree_rend_le_relatif_si_le_paquet_ne_l_a_pas(gel, monkeypatch,
                                                                     tmp_path):
    monkeypatch.chdir(tmp_path)
    assert ins.donnee_livree("inexistant") == Path("inexistant")


# --------------------------------------------------------------------------- #
#  Piège 1 — la copie se fait une fois, et jamais deux
# --------------------------------------------------------------------------- #

def test_le_premier_lancement_copie_le_config_livre(gel):
    (gel / "config.yaml").write_text("langues:\n  cible: fr\n", encoding="utf-8")
    ecrit = ins.installer_config_utilisateur()
    assert ecrit == ins.config_utilisateur()
    assert ecrit.read_text(encoding="utf-8") == "langues:\n  cible: fr\n"


def test_la_copie_n_est_jamais_remplacee(gel):
    """⚠ LE test du piège 1. Une mise à jour apporte un `config.yaml` livré différent ; la
    copie de l'utilisateur porte ses réglages, et elle gagne."""
    (gel / "config.yaml").write_text("livre: 1\n", encoding="utf-8")
    ins.installer_config_utilisateur()
    ins.config_utilisateur().write_text("edite_a_la_main: oui\n", encoding="utf-8")

    (gel / "config.yaml").write_text("livre: 2\n", encoding="utf-8")
    assert ins.installer_config_utilisateur() is None
    assert ins.config_utilisateur().read_text(encoding="utf-8") == "edite_a_la_main: oui\n"


def test_le_config_livre_n_est_jamais_reecrit(gel):
    """Interdit 5 : 158 Ko de prose qu'un aller-retour `safe_dump` effacerait. L'empreinte du
    fichier livré est la même avant et après un cycle complet de résolution."""
    livre = gel / "config.yaml"
    livre.write_bytes((RACINE / "config.yaml").read_bytes())
    avant = hashlib.sha256(livre.read_bytes()).hexdigest()

    chemin = ins.resoudre_config(None)
    config = yaml.safe_load(Path(chemin).read_text(encoding="utf-8"))
    ins.ancrer_chemins(config)
    ins.ecart_de_config()

    assert hashlib.sha256(livre.read_bytes()).hexdigest() == avant


def test_la_copie_utilisateur_est_octet_pour_octet_celle_du_depot(gel):
    """La copie se fait par `shutil.copy2`, pas par un aller-retour YAML — donc les 158 Ko de
    commentaires arrivent intacts chez l'utilisateur."""
    livre = gel / "config.yaml"
    livre.write_bytes((RACINE / "config.yaml").read_bytes())
    ins.installer_config_utilisateur()
    assert ins.empreinte(ins.config_utilisateur()) == ins.empreinte(RACINE / "config.yaml")


def test_resoudre_config_suit_les_trois_rangs(gel):
    (gel / "config.yaml").write_text("livre: 1\n", encoding="utf-8")
    # Rang 3 puis 2 : la copie est créée, donc c'est elle qui sort.
    assert ins.resoudre_config(None) == ins.config_utilisateur()
    # Rang 1 : l'argument explicite gagne, gelé ou non.
    assert ins.resoudre_config("D:/ailleurs.yaml") == Path("D:/ailleurs.yaml")


def test_le_fichier_livre_sert_de_repli_si_la_copie_echoue(gel, monkeypatch):
    (gel / "config.yaml").write_text("livre: 1\n", encoding="utf-8")
    monkeypatch.setattr(ins, "installer_config_utilisateur", lambda **_: None)
    assert ins.resoudre_config(None) == ins.config_livree()


# --------------------------------------------------------------------------- #
#  Piège 2 — l'écart se DIT, il ne se fusionne pas
# --------------------------------------------------------------------------- #

def test_deux_fichiers_identiques_n_ont_rien_a_signaler(gel):
    (gel / "config.yaml").write_text("a: 1\n", encoding="utf-8")
    ins.installer_config_utilisateur()
    ecart = ins.ecart_de_config()
    assert ecart.identiques and not ecart.a_signaler and ecart.phrase() == ""


def test_une_cle_ajoutee_par_la_mise_a_jour_est_nommee(gel):
    from core.version import __version__
    (gel / "config.yaml").write_text("a: 1\n", encoding="utf-8")
    ins.installer_config_utilisateur()
    (gel / "config.yaml").write_text("a: 1\nmaj:\n  verifier: false\n", encoding="utf-8")

    ecart = ins.ecart_de_config()
    assert ecart.a_signaler
    assert ecart.cles_ajoutees == ("maj", "maj.verifier")
    assert ecart.version_copie == __version__
    assert "2 clé(s) ajoutée(s)" in ecart.phrase()
    assert "maj.verifier" in ecart.phrase()


def test_l_ecart_ne_touche_a_aucun_des_deux_fichiers(gel):
    (gel / "config.yaml").write_text("a: 1\n", encoding="utf-8")
    ins.installer_config_utilisateur()
    (gel / "config.yaml").write_text("a: 1\nb: 2\n", encoding="utf-8")
    empreintes = (ins.empreinte(gel / "config.yaml"),
                  ins.empreinte(ins.config_utilisateur()))
    ins.ecart_de_config()
    assert (ins.empreinte(gel / "config.yaml"),
            ins.empreinte(ins.config_utilisateur())) == empreintes


def test_sans_copie_l_ecart_se_declare_illisible(gel):
    ecart = ins.ecart_de_config()
    assert not ecart.lisible and not ecart.a_signaler


# --------------------------------------------------------------------------- #
#  Piège 3 — les œuvres ne vivent pas dans le dossier d'installation
# --------------------------------------------------------------------------- #

def test_en_gel_les_oeuvres_vont_dans_les_documents(gel):
    config = {"chemins": {"sources": "sources", "build": "build"}}
    ins.ancrer_chemins(config)
    documents = ins.dossier_documents()
    assert Path(config["chemins"]["sources"]) == documents / "sources"
    assert Path(config["chemins"]["build"]) == documents / "build"


def test_en_gel_aucun_chemin_d_oeuvre_ne_tombe_dans_l_installation(gel):
    """Le critère 9 du plan, énoncé comme une propriété plutôt que comme une valeur."""
    config = yaml.safe_load((RACINE / "config.yaml").read_text(encoding="utf-8"))
    ins.ancrer_chemins(config)
    livree = str(ins.racine_livree())
    for pointee in ins.CHEMINS_D_OEUVRES + ins.CHEMINS_DE_POIDS:
        noeud = config
        for segment in pointee.split("."):
            noeud = (noeud or {}).get(segment)
        if noeud:
            assert not str(noeud).startswith(livree), f"{pointee} → {noeud}"


def test_en_gel_les_poids_vont_dans_le_dossier_utilisateur(gel):
    """Aucun poids n'est livré (`PLAN-37` §0.3) : ils sont téléchargés, donc ils atterrissent
    là où l'on peut écrire et où une mise à jour ne passe pas."""
    config = {"manga": {"detection": {"model_path": "manga_models/bubble_detector.onnx"}}}
    ins.ancrer_chemins(config)
    attendu = ins.dossier_utilisateur() / "manga_models" / "bubble_detector.onnx"
    assert Path(config["manga"]["detection"]["model_path"]) == attendu


def test_un_chemin_absolu_n_est_jamais_deplace(gel):
    """Quelqu'un qui a écrit `D:/Manga/sources` l'a voulu."""
    config = {"chemins": {"sources": "D:/Manga/sources", "build": "build"}}
    ins.ancrer_chemins(config)
    assert config["chemins"]["sources"] == "D:/Manga/sources"


def test_la_section_manga_est_ancree_aussi(gel):
    """`core/config.py` fait un héritage PROFOND : la brique manga peut porter ses propres
    chemins, et n'ancrer que la racine la laisserait écrire dans l'installation."""
    config = {"manga": {"chemins": {"sources": "sources", "build": "build"}}}
    ins.ancrer_chemins(config)
    assert Path(config["manga"]["chemins"]["build"]) == ins.dossier_documents() / "build"


def test_une_config_sans_les_cles_ne_leve_pas(gel):
    assert ins.ancrer_chemins({}) == {}
    assert ins.ancrer_chemins({"chemins": None}) == {"chemins": None}


# --------------------------------------------------------------------------- #
#  `.angelith/` — la variable préexistait, seul le défaut est neuf
# --------------------------------------------------------------------------- #

def test_en_gel_les_reglages_vont_dans_le_dossier_utilisateur(gel):
    from gui import reglages
    assert ins.dossier_reglages() == ins.dossier_utilisateur()
    assert reglages.chemin() == ins.dossier_utilisateur() / ".angelith" / "interface.json"


def test_la_variable_d_environnement_l_emporte_toujours(gel, monkeypatch, tmp_path):
    from gui import profils, reglages
    monkeypatch.setenv(reglages.VARIABLE, str(tmp_path / "force.json"))
    monkeypatch.setenv(profils.VARIABLE, str(tmp_path / "profils.json"))
    assert reglages.chemin() == tmp_path / "force.json"
    assert profils.chemin() == tmp_path / "profils.json"


# --------------------------------------------------------------------------- #
#  L'écart de version, tel que le DIAGNOSTIC le dit — critère 8, seconde moitié
# --------------------------------------------------------------------------- #

def test_hors_gel_le_diagnostic_ne_parle_pas_d_installation():
    """Le critère 3, une fois de plus : rien de neuf n'apparaît dans le dépôt."""
    from core import diagnostic as diag
    assert diag.section_installation() is None


def test_en_gel_sans_ecart_le_diagnostic_se_tait(gel):
    from core import diagnostic as diag
    (gel / "config.yaml").write_text("a: 1\n", encoding="utf-8")
    ins.installer_config_utilisateur()
    assert diag.section_installation() is None


def test_en_gel_avec_ecart_le_diagnostic_nomme_les_cles(gel):
    """⚠ `INFORMATION` et pas `DEGRADE` : un `config.yaml` antérieur MARCHE — les clés absentes
    prennent leur valeur par défaut. Ce qui manque est de la connaissance, pas du
    fonctionnement, et un faux avertissement cesse d'être lu."""
    from core import diagnostic as diag
    (gel / "config.yaml").write_text("a: 1\n", encoding="utf-8")
    ins.installer_config_utilisateur()
    (gel / "config.yaml").write_text("a: 1\nmaj:\n  verifier: false\n", encoding="utf-8")

    section = diag.section_installation()
    assert section is not None
    verdict = section.verdicts[0]
    assert verdict.gravite == diag.INFORMATION
    assert verdict.identifiant == "config_utilisateur_datee"
    assert "maj.verifier" in verdict.constat
    assert verdict.geste and not verdict.reparable


def test_le_geste_ne_propose_jamais_de_fusionner(gel):
    """On ne fusionne pas un document (interdit 5). Le geste nomme les deux fichiers."""
    from core import diagnostic as diag
    (gel / "config.yaml").write_text("a: 1\n", encoding="utf-8")
    ins.installer_config_utilisateur()
    (gel / "config.yaml").write_text("a: 1\nb: 2\n", encoding="utf-8")
    geste = diag.section_installation().verdicts[0].geste
    assert "fusionne pas" in geste
    assert str(ins.config_utilisateur()) in geste
    assert str(ins.config_livree()) in geste
