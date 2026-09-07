# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Alexandre Tournel

"""`tools/juge_humain.py` — l'outil du protocole en aveugle, et ce qu'il ne doit pas faire.

Trois propriétés se testent ici, et aucune ne se relit :

1. **il ne génère rien et ne réencode rien** — les copies présentées sont des copies OCTET
   POUR OCTET, donc le bloc `tEXt` qui déclare l'image générée par IA voyage avec elles. Une
   copie passée par Pillow perdrait le marquage, et la brique livrerait une image non marquée
   par une porte dérobée ;
2. **le nom d'un fichier est une étiquette** — `paire-07-A.png` ne dit rien de la
   configuration, et l'ordre d'écriture sur le disque non plus ;
3. **un encodeur absent rend « non mesuré », jamais un accord de 0 %.**
"""
import json

import pytest

from illustration import aveugle as aveugle_mod
from tools import juge_humain as outil

pytest.importorskip("PIL")


def _png_marque(chemin, texte="généré par IA"):
    """Un PNG portant un bloc `tEXt` — l'équivalent minimal de ce que `marquage.ecrire` pose."""
    from PIL import Image, PngImagePlugin

    info = PngImagePlugin.PngInfo()
    info.add_text("Comment", texte)
    info.add_text("AIGenerated", "true")
    Image.new("RGB", (8, 8), (200, 30, 30)).save(chemin, pnginfo=info)
    return chemin


def _dossier_de_balayage(tmp_path, noms=("force-r2-p6-g1", "nombre_references-r1-p4-g1",
                                         "nombre_references-r3-p4-g1")):
    dossier = tmp_path / "balayage"
    dossier.mkdir(parents=True)
    for nom in noms:
        _png_marque(dossier / f"{nom}.png")
    return dossier


# ────────────────────────────  Trouver le matériel  ────────────────────────────

def test_la_configuration_vient_du_nom_du_fichier(tmp_path):
    liste = outil.candidats(_dossier_de_balayage(tmp_path))
    assert {c["configuration"] for c in liste} == {
        "force-r2-p6-g1", "nombre_references-r1-p4-g1", "nombre_references-r3-p4-g1"}


def test_le_sidecar_etiquette_les_images_qui_ne_viennent_PAS_du_balayage(tmp_path):
    """⚠ Deux portraits du même personnage produits par l'atelier portent le même nom de
    fichier racine : sans le sidecar, le protocole les croirait de même configuration.

    ⚠ Les champs lus sont **ceux que `_bloc_prompt` écrit** — une clé inventée ici rendrait
    « configuration inconnue » sur toutes les images sans que rien ne le dise."""
    from illustration import marquage

    dossier = _dossier_de_balayage(tmp_path, noms=("tory",))
    marquage.manifeste_de(dossier / "tory.png").write_text(
        json.dumps({"prompt_source": {"forme": "prose", "langue": "fr",
                                      "cadrage": "buste", "decor": "trame"}}),
        encoding="utf-8")
    assert outil.candidats(dossier)[0]["configuration"] == "prose-fr-buste-trame"


def test_une_image_de_BALAYAGE_garde_son_nom_sans_qu_on_le_devine(tmp_path):
    """⚠ `banc_identite._ecrire_image` ne passe **pas** de `prompt_source` à son manifeste :
    une image de balayage n'en porte donc aucun et retombe d'elle-même sur son nom. Aucune
    heuristique n'est nécessaire — et celle qu'on avait écrite (« un tiret = un nom de
    balayage ») se serait trompée au premier personnage à deux mots."""
    from illustration import marquage

    dossier = _dossier_de_balayage(tmp_path, noms=("force-r2-p6-g1-neutre",))
    marquage.manifeste_de(dossier / "force-r2-p6-g1-neutre.png").write_text(
        json.dumps({"schema": 1, "genere_par_ia": True}), encoding="utf-8")
    assert outil.candidats(dossier)[0]["configuration"] == "force-r2-p6-g1-neutre"


def test_un_personnage_a_DEUX_MOTS_n_est_pas_pris_pour_un_nom_de_balayage(tmp_path):
    """`illustration/requete.py:_ardoise("Tory Noelle")` rend `tory-noelle`. C'est le cas que
    l'heuristique du tiret aurait manqué."""
    from illustration import marquage

    dossier = _dossier_de_balayage(tmp_path, noms=("tory-noelle",))
    marquage.manifeste_de(dossier / "tory-noelle.png").write_text(
        json.dumps({"prompt_source": {"decor": "trame", "cadrage": "buste"}}),
        encoding="utf-8")
    assert outil.candidats(dossier)[0]["configuration"] == "buste-trame"


def test_le_sidecar_est_cherche_sous_le_nom_que_le_MARQUAGE_ecrit(tmp_path):
    """⚠ Le test qui a rattrapé une erreur de ce lot : le sidecar s'appelle
    `<image>.png.provenance.json`, pas `<image>.png.json`. Une seconde règle de nommage écrite
    ici aurait cherché un fichier qui n'existe jamais, et l'étiquetage aurait échoué en
    silence sur toutes les images de l'atelier."""
    from illustration import marquage

    assert marquage.manifeste_de(tmp_path / "a.png").name == "a.png.provenance.json"


def test_un_sidecar_illisible_ne_fait_pas_tomber_l_outil(tmp_path):
    from illustration import marquage

    dossier = _dossier_de_balayage(tmp_path, noms=("a",))
    marquage.manifeste_de(dossier / "a.png").write_text("{pas du JSON", encoding="utf-8")
    assert outil.candidats(dossier)[0]["configuration"] == "a"


def test_un_dossier_absent_rend_une_liste_vide(tmp_path):
    assert outil.candidats(tmp_path / "nulle_part") == []


# ────────────────────  La copie : marquée, neutre, et dans le désordre  ────────────────────

def _creer(tmp_path, **extra):
    dossier = _dossier_de_balayage(tmp_path)
    liste = aveugle_mod.paires(outil.candidats(dossier), nombre=3, graine=5)
    cible = tmp_path / "aveugle"
    defauts = {"reference": "", "seuil": 2, "graine": 5, "juge": {}}
    return cible, outil.creer(cible, liste, **{**defauts, **extra})


def test_la_copie_garde_le_bloc_tEXt_de_l_originale(tmp_path):
    """⚠ **La propriété qui compte le plus de ce fichier.** Une copie réencodée par Pillow
    perdrait `AIGenerated`, et l'outil deviendrait un chemin par lequel une image générée
    circule sans son marquage."""
    from PIL import Image

    cible, doc = _creer(tmp_path)
    copie = cible / outil.DOSSIER_IMAGES / doc["paires"][0]["copie_A"]
    with Image.open(copie) as image:
        assert image.text["AIGenerated"] == "true"
        assert "généré par IA" in image.text["Comment"]


def test_la_copie_est_octet_pour_octet(tmp_path):
    cible, doc = _creer(tmp_path)
    paire = doc["paires"][0]
    originale = (tmp_path / "balayage" / f"{paire['_config_gauche']}.png").read_bytes()
    assert (cible / outil.DOSSIER_IMAGES / paire["copie_A"]).read_bytes() == originale


def test_le_nom_presente_ne_dit_rien_de_la_configuration(tmp_path):
    cible, doc = _creer(tmp_path)
    for fichier in (cible / outil.DOSSIER_IMAGES).iterdir():
        assert fichier.name.startswith("paire-")
        assert "force" not in fichier.name and "references" not in fichier.name


def test_la_copie_n_HERITE_PAS_de_la_date_de_l_originale(tmp_path, monkeypatch):
    """⚠ **Le test qui a fait changer une ligne.** `shutil.copy2` recopie les métadonnées,
    **date de modification comprise** : les copies héritaient de la date de l'image d'origine,
    et un dossier trié par date rendait l'ordre dans lequel le balayage avait généré — donc
    l'ordre des configurations. Mélanger l'ordre d'écriture ne servait à rien tant que la date
    suivait le fichier. C'est la fuite que la règle 2 de L29.2 nomme.

    ⚠ Testé sur la fonction APPELÉE et non sur les dates du disque : la granularité d'horloge
    de Windows est d'environ 15 ms, et deux fichiers écrits dans le même tic portent la même
    date à la nanoseconde près. Un test qui comparerait des `st_mtime_ns` passerait ou
    échouerait selon la vitesse de la machine, ce qui n'est pas une garantie."""
    appels: list[str] = []
    for nom in ("copy2", "copystat", "copymode"):
        monkeypatch.setattr(outil.shutil, nom,
                            lambda *a, _n=nom, **k: appels.append(_n))
    _creer(tmp_path)
    assert not appels, f"{appels} recopie(nt) la date, donc l'ordre du balayage"


def test_l_ordre_d_ECRITURE_ne_suit_pas_l_ordre_des_paires(tmp_path, monkeypatch):
    """Testé sur l'ordre des appels, et non sur les dates du disque : la résolution d'horloge
    d'un système de fichiers n'est pas une garantie sur laquelle asseoir un protocole."""
    ecrites: list[str] = []
    vraie = outil.shutil.copyfile
    monkeypatch.setattr(outil.shutil, "copyfile",
                        lambda s, d: (ecrites.append(str(d)), vraie(s, d))[1])
    _creer(tmp_path)
    assert ecrites != sorted(ecrites), "les copies sont écrites dans l'ordre des paires"


def test_le_protocole_ecrit_porte_son_seuil_et_sa_correspondance(tmp_path):
    cible, _ = _creer(tmp_path, seuil=14)
    doc = json.loads((cible / aveugle_mod.NOM_PROTOCOLE).read_text(encoding="utf-8"))
    assert doc["seuil"] == 14
    assert all("_config_gauche" in p and "copie_A" in p for p in doc["paires"])


# ────────────────────────────  L'accord, et son absence  ────────────────────────────

def test_sans_reference_il_n_y_a_pas_d_accord_a_calculer_et_le_motif_le_dit(tmp_path):
    _, doc = _creer(tmp_path, reference="")
    scores, motif = outil.scores_automatiques(doc, "peu importe")
    assert scores == {}
    assert "référence" in motif


def test_un_encodeur_absent_donne_NON_MESURE_et_pas_un_accord_de_zero(tmp_path):
    cible, doc = _creer(tmp_path, reference=str(tmp_path / "balayage" / "a.png"))
    scores, motif = outil.scores_automatiques(doc, str(tmp_path / "aucun-encodeur.onnx"))
    assert scores == {}
    assert "absence de mesure" in motif

    resultat = aveugle_mod.rapport(doc, [], scores or None)
    lignes = "\n".join(outil.rendre(doc, resultat, motif, markdown=False))
    assert "non mesuré" in lignes
    assert "0 %" not in lignes


def test_le_rapport_ne_publie_PAS_la_configuration_dans_le_tableau_detaille(tmp_path):
    """La correspondance vit dans `protocole.json`. La publier dans le rapport rendrait le
    matériel inutilisable pour une seconde passe sur les mêmes images."""
    cible, doc = _creer(tmp_path)
    resultat = aveugle_mod.rapport(doc, [aveugle_mod.reponse(1, "A")])
    lignes = "\n".join(outil.rendre(doc, resultat, "", markdown=True))
    assert "force-r2-p6-g1" not in lignes
    assert "humain" in lignes and "automatique" in lignes


# ──────────────────  Ce que l'outil ne fait pas : générer  ──────────────────

def test_l_outil_n_importe_aucun_moteur_et_ne_sait_pas_generer():
    """⚠ Générer reste le travail de `run_illustration.py`, qui porte la porte humaine et le
    marquage. Un second chemin capable d'envoyer un `/prompt` serait une seconde porte, non
    gardée — c'est la propriété que le lot 28 a comptée pour `tools/comfy.py`, tenue ici
    aussi."""
    import ast
    import pathlib

    source = pathlib.Path(outil.__file__).read_text(encoding="utf-8")
    arbre = ast.parse(source)
    appels = {n.attr for n in ast.walk(arbre) if isinstance(n, ast.Attribute)}
    assert "generer" not in appels
    for interdit in ("construire_moteur", "Requete", "ComfyUI"):
        assert interdit not in source, f"« {interdit} » ouvrirait une seconde porte"


def test_l_outil_n_ecrit_aucun_PNG_par_encodage(tmp_path):
    """Il copie ; il ne fabrique pas. `Image.save` ici serait le début d'un chemin qui écrit
    des pixels hors de `marquage.ecrire`."""
    import pathlib

    source = pathlib.Path(outil.__file__).read_text(encoding="utf-8")
    assert ".save(" not in source
    assert "shutil.copyfile" in source
    assert "shutil.copy2" not in source, "copy2 recopierait la date, donc l'ordre du balayage"
