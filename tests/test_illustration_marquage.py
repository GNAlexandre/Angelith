# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Alexandre Tournel

"""Le marquage AI Act — **inamovible**, et sans chemin de contournement.

Le `PLAN-24` critère 7 demande deux tests, et ce fichier les porte :

1. **le marquage tient** — générer, relire le PNG, retrouver tous les champs ;
2. **aucun chemin de code ne sait produire un PNG sans marquage** — c'est-à-dire que
   l'écriture passe par une seule fonction. Ce second test est statique : il lit les sources
   de `illustration/` et échoue si un autre module sait écrire des octets d'image.

Un test statique se contourne (un `getattr`, un `exec`), et le dire vaut mieux que de laisser
croire le contraire. Ce qu'il attrape est le cas réel : quelqu'un qui ajoute un `--brut` ou un
export « sans métadonnées » six mois plus tard, de bonne foi, parce que c'était pratique.
"""
import json
import re
from dataclasses import replace
from pathlib import Path

import pytest

from core.version import __version__
from illustration import marquage
from illustration.moteur import MoteurFactice, Requete

RACINE = Path(__file__).resolve().parent.parent


def _sortie(**champs):
    return MoteurFactice().generer(Requete(prompt="une jeune femme", graine=7, **champs))


def _provenance(**champs):
    requete = Requete(prompt="une jeune femme, cheveux blonds", graine=7, modele="modele-test")
    base = marquage.manifeste(
        requete, _sortie(), projet="Projet Témoin", tome="Vol.1",
        identifiant=marquage.identifiant_oeuvre("Projet Témoin", "Vol.1"),
        validation={"par": "Alexandre", "date": "2026-08-29"},
        config_sha256="c" * 64, poids_sha256="p" * 64, modele="modele-test")
    base.update(champs)
    return requete, base


# ────────────────────────────  1. Le marquage tient  ────────────────────────────

def test_tous_les_champs_tEXt_sont_relus_dans_le_PNG(tmp_path):
    requete, provenance = _provenance()
    image, _ = marquage.ecrire(_sortie(), tmp_path / "a.png", provenance=provenance)
    champs = marquage.relire(image)
    assert set(marquage.CHAMPS_PNG) <= set(champs)
    assert champs["AIGenerated"] == "true"
    assert champs["Software"] == f"Angelith {__version__}"
    assert champs["Seed"] == "7"
    assert champs["Disclaimer"] == marquage.PHRASE_NON_OEUVRE
    assert "modele-test" in champs["Generator"]
    assert requete.prompt in champs["Prompt"]


def test_le_sidecar_porte_le_payload_EXACT_envoye_au_moteur(tmp_path):
    """Critère 7 : « le sidecar archive le payload JSON exact envoyé au moteur, canaux
    compris ». C'est lui qui rend le rejeu possible."""
    requete, provenance = _provenance()
    _, manifeste = marquage.ecrire(_sortie(), tmp_path / "a.png", provenance=provenance)
    lu = json.loads(manifeste.read_text(encoding="utf-8"))
    assert lu["payload"] == requete.payload()
    assert Requete.depuis_payload(lu["payload"]) == requete


def test_le_sidecar_porte_la_validation_humaine(tmp_path):
    """« Aucun PNG n'existe sans qu'un humain ait validé le prompt qui l'a produit » — la
    ligne exacte que la politique IA du dossier NLnet exige de pouvoir montrer."""
    _, provenance = _provenance()
    _, manifeste = marquage.ecrire(_sortie(), tmp_path / "a.png", provenance=provenance)
    lu = json.loads(manifeste.read_text(encoding="utf-8"))
    assert lu["validation_humaine"]["par"] == "Alexandre"
    assert lu["genere_par_ia"] is True
    assert lu["avertissement"] == marquage.PHRASE_NON_OEUVRE


def test_le_sidecar_porte_les_empreintes_de_config_et_de_poids(tmp_path):
    _, provenance = _provenance()
    _, manifeste = marquage.ecrire(_sortie(), tmp_path / "a.png", provenance=provenance)
    lu = json.loads(manifeste.read_text(encoding="utf-8"))
    assert lu["config_sha256"] == "c" * 64 and lu["poids_sha256"] == "p" * 64
    assert lu["requete_sha256"] and lu["image_sha256"]


def test_l_empreinte_du_sidecar_est_celle_du_fichier_ecrit(tmp_path):
    """Une empreinte calculée sur les octets AVANT écriture ne décrirait pas le fichier
    livré : le PNG réécrit par Pillow avec ses chunks n'est plus celui du moteur."""
    _, provenance = _provenance()
    image, manifeste = marquage.ecrire(_sortie(), tmp_path / "a.png", provenance=provenance)
    lu = json.loads(manifeste.read_text(encoding="utf-8"))
    assert lu["image_sha256"] == marquage.empreinte_fichier(image)


def test_le_prompt_est_tronque_dans_le_PNG_mais_entier_dans_le_sidecar(tmp_path):
    long = "cheveux blonds, " * 200
    requete = Requete(prompt=long, graine=1, modele="m")
    provenance = marquage.manifeste(
        requete, _sortie(), projet="P", tome="V", identifiant="oeuvre-abc",
        validation={"par": "x"}, modele="m")
    image, manifeste = marquage.ecrire(_sortie(), tmp_path / "a.png", provenance=provenance)
    assert len(marquage.relire(image)["Prompt"]) <= marquage.PROMPT_MAX
    assert json.loads(manifeste.read_text(encoding="utf-8"))["payload"]["prompt"] == long


def test_le_manifeste_se_trouve_a_cote_de_l_image(tmp_path):
    _, provenance = _provenance()
    image, manifeste = marquage.ecrire(_sortie(), tmp_path / "a.png", provenance=provenance)
    assert manifeste == marquage.manifeste_de(image)
    assert manifeste.name == "a.png.provenance.json"


# ─────────────────  Le titre de l'œuvre n'entre pas dans les métadonnées  ─────────────────

# ───────────  1 bis. Le graphe envoyé, à côté de l'image — L28.3  ───────────

def test_le_graphe_envoye_est_ecrit_A_COTE_de_l_image(tmp_path):
    """⚠ **La différence entre une trace et un souvenir.** Un run qui a produit une image
    étrange ne laissait aucun moyen de savoir dans quel régime il avait tourné."""
    requete, provenance = _provenance()
    provenance["_graphe"] = {"1": {"class_type": "KSampler", "inputs": {"seed": 7}}}
    image, manifeste = marquage.ecrire(_sortie(), tmp_path / "a.png",
                                       provenance=provenance)
    graphe = marquage.graphe_de(image)
    assert graphe.is_file() and graphe.name == "a.png.graphe.json"
    assert json.loads(graphe.read_text(encoding="utf-8"))["1"]["class_type"] == "KSampler"


def test_le_sidecar_porte_la_REFERENCE_du_graphe_et_pas_le_graphe(tmp_path):
    """Un manifeste dans lequel le graphe serait recopié ferait des kilo-octets par image et
    deviendrait illisible à l'œil — or c'est le fichier qu'un humain ouvre."""
    requete, provenance = _provenance()
    provenance["_graphe"] = {"1": {"class_type": "KSampler", "inputs": {"seed": 7}}}
    _, manifeste = marquage.ecrire(_sortie(), tmp_path / "a.png", provenance=provenance)
    donnees = json.loads(manifeste.read_text(encoding="utf-8"))
    assert donnees["graphe"]["fichier"] == "a.png.graphe.json"
    assert len(donnees["graphe"]["sha256"]) == 64
    assert "class_type" not in json.dumps(donnees["graphe"])


def test_le_graphe_ne_va_PAS_dans_le_bloc_tEXt_du_png(tmp_path):
    """⚠ Le `tEXt` porte l'identité de l'image, pas un JSON de plusieurs kilo-octets — le
    `PLAN-28` L28.3 l'écrit noir sur blanc."""
    requete, provenance = _provenance()
    provenance["_graphe"] = {"1": {"class_type": "KSampler", "inputs": {"seed": 7}}}
    image, _ = marquage.ecrire(_sortie(), tmp_path / "a.png", provenance=provenance)
    assert "class_type" not in json.dumps(marquage.relire(image))


def test_les_lignes_de_journal_du_serveur_sont_archivees(tmp_path):
    requete, provenance = _provenance()
    provenance["journal_serveur"] = {"disponible": True, "rogne": True,
                                     "lignes": ["loaded partially lowvram patches: 42"]}
    _, manifeste = marquage.ecrire(_sortie(), tmp_path / "a.png", provenance=provenance)
    donnees = json.loads(manifeste.read_text(encoding="utf-8"))
    assert donnees["journal_serveur"]["rogne"] is True


def test_sans_graphe_aucun_fichier_de_graphe_n_est_ecrit(tmp_path):
    """Le moteur factice n'en construit aucun : un fichier vide vaudrait moins que son
    absence, et `--journal` sait dire « ABSENT »."""
    requete, provenance = _provenance()
    image, manifeste = marquage.ecrire(_sortie(), tmp_path / "a.png", provenance=provenance)
    assert not marquage.graphe_de(image).exists()
    assert "graphe" not in json.loads(manifeste.read_text(encoding="utf-8"))


def test_le_graphe_du_moteur_comfy_atterrit_dans_le_manifeste(tmp_path):
    """De bout en bout : ce que le client met dans `Sortie.provenance` ressort en fichier."""
    from illustration.comfyui import MoteurComfyUI
    from tests.test_illustration_moteur import _TransportFactice

    chemin = tmp_path / "w.api.json"
    chemin.write_text(json.dumps({
        "3": {"class_type": "CLIPTextEncode", "inputs": {"text": "%prompt%"}},
        "7": {"class_type": "KSampler", "inputs": {"seed": "%graine%"}}}), encoding="utf-8")
    moteur = MoteurComfyUI(chemin, transport=_TransportFactice(), attente=lambda _s: None)
    sortie = moteur.generer(Requete(prompt="une jeune femme", graine=7))
    assert sortie.provenance["graphe"]["7"]["inputs"]["seed"] == 7
    # Le transport factice ne rend pas un vrai PNG : on garde SA provenance et les octets
    # d'un PNG valide, puisque c'est le chemin de la provenance qu'on mesure ici.
    sortie = replace(sortie, png=_sortie().png)
    provenance = marquage.manifeste(
        Requete(prompt="une jeune femme", graine=7), sortie, projet="P", tome="T",
        identifiant="oeuvre-x", validation={"par": "A", "date": "2026-09-02"},
        modele="modele-test")
    # Le graphe n'est PAS resté dans `moteur_details`, qui est un dictionnaire de diagnostic.
    assert "graphe" not in provenance["moteur_details"]
    image, manifeste = marquage.ecrire(sortie, tmp_path / "b.png", provenance=provenance)
    assert marquage.graphe_de(image).is_file()


def test_l_identifiant_est_un_digest_stable_et_pas_le_titre():
    a = marquage.identifiant_oeuvre("Projet Témoin", "Vol.1")
    b = marquage.identifiant_oeuvre("Projet Témoin", "Vol.1")
    assert a == b and a.startswith("oeuvre-") and "Témoin" not in a
    assert marquage.identifiant_oeuvre("Autre", "Vol.1") != a


def test_un_prompt_qui_nomme_l_oeuvre_fait_LEVER_plutot_que_censurer(tmp_path):
    """Retirer silencieusement le titre changerait le prompt archivé, donc casserait le
    rejeu, donc mentirait sur ce qui a été envoyé au modèle."""
    requete = Requete(prompt="illustration pour Projet Témoin", graine=1, modele="m")
    provenance = marquage.manifeste(requete, _sortie(), projet="Projet Témoin", tome="Vol.1",
                                    identifiant="oeuvre-abc", validation={"par": "x"},
                                    modele="m")
    with pytest.raises(marquage.MarquageImpossible) as echec:
        marquage.ecrire(_sortie(), tmp_path / "a.png", provenance=provenance)
    assert "Projet Témoin" in str(echec.value)
    assert not (tmp_path / "a.png").exists()


def test_un_nom_de_tome_trop_court_ne_declenche_pas_de_faux_positif(tmp_path):
    """« V1 » ferait lever sur n'importe quel prompt contenant « v1 ». Le garde exige trois
    caractères : mieux vaut un garde qui laisse passer un cas rare qu'un garde qu'on désarme
    parce qu'il crie tout le temps."""
    requete = Requete(prompt="une jeune femme", graine=1, modele="m")
    provenance = marquage.manifeste(requete, _sortie(), projet="X", tome="V1",
                                    identifiant="oeuvre-abc", validation={"par": "x"},
                                    modele="m")
    marquage.ecrire(_sortie(), tmp_path / "a.png", provenance=provenance)


# ─────────────────  2. Aucun chemin de code ne produit un PNG nu  ─────────────────

def test_un_marquage_incomplet_refuse_d_ecrire_l_image(tmp_path):
    _, provenance = _provenance()
    provenance["oeuvre"] = ""                             # SourceWork vide
    with pytest.raises(marquage.MarquageImpossible):
        marquage.ecrire(_sortie(), tmp_path / "a.png", provenance=provenance)
    assert not (tmp_path / "a.png").exists()
    assert not (tmp_path / "a.png.provenance.json").exists()


def test_un_format_autre_que_PNG_est_refuse(tmp_path):
    """Un JPEG perdrait les blocs tEXt sans un mot — donc le marquage avec."""
    _, provenance = _provenance()
    with pytest.raises(marquage.MarquageImpossible) as echec:
        marquage.ecrire(_sortie(), tmp_path / "a.jpg", provenance=provenance)
    assert "PNG" in str(echec.value)


def test_aucun_chemin_de_code_ne_sait_ecrire_une_image_sans_marquage(tmp_path):
    """Critère 7, second test — et il est **dynamique**, pas un `grep` sur les sources.

    Un test statique se contourne d'un `getattr` ou d'un `exec` ; celui-ci constate au
    moment de l'écriture. Tant qu'un périmètre est armé, tout fichier d'extension image est
    refusé sauf dans le bloc `frontiere.ecriture_marquee()`, dont `marquage.ecrire` est le
    seul appelant du dépôt."""
    from PIL import Image

    from illustration import frontiere

    with frontiere.perimetre(tmp_path):
        for nom in ("brute.png", "sortie.jpg", "planche.webp"):
            with pytest.raises(frontiere.ImageNonMarquee):
                Image.new("RGB", (4, 4)).save(tmp_path / nom)
            with pytest.raises(frontiere.ImageNonMarquee):
                (tmp_path / nom).write_bytes(b"\x89PNG")
            assert not (tmp_path / nom).exists()
        # Et le texte, lui, passe : le garde vise les images, pas le dossier.
        (tmp_path / "note.md").write_text("ok", encoding="utf-8")


def test_le_chemin_marque_est_le_seul_a_passer_le_garde(tmp_path):
    from illustration import frontiere

    _, provenance = _provenance()
    with frontiere.perimetre(tmp_path):
        image, manifeste = marquage.ecrire(_sortie(), tmp_path / "a.png",
                                           provenance=provenance)
    assert image.is_file() and manifeste.is_file()
    assert marquage.relire(image)["AIGenerated"] == "true"


def test_le_drapeau_retombe_meme_sur_exception(tmp_path):
    """Sans ça, un marquage qui lève laisserait la porte ouverte pour tout le reste du run."""
    from illustration import frontiere

    _, provenance = _provenance()
    provenance["oeuvre"] = ""                             # fera lever MarquageImpossible
    with frontiere.perimetre(tmp_path):
        with pytest.raises(marquage.MarquageImpossible):
            marquage.ecrire(_sortie(), tmp_path / "a.png", provenance=provenance)
        with pytest.raises(frontiere.ImageNonMarquee):
            (tmp_path / "b.png").write_bytes(b"\x89PNG")


def test_seul_marquage_py_leve_le_drapeau_d_ecriture_d_image():
    """Le pendant statique, réduit à ce qu'il sait dire avec certitude : un seul module
    appelle `ecriture_marquee`. Le nom est explicite pour que l'ajouter ailleurs demande de
    l'écrire noir sur blanc — c'est-à-dire de désarmer consciemment le marquage."""
    appelants = [source.name for source in (RACINE / "illustration").glob("*.py")
                 if re.search(r"ecriture_marquee\s*\(",
                              source.read_text(encoding="utf-8").replace(
                                  "def ecriture_marquee(", ""))]
    assert appelants == ["marquage.py"], appelants


def test_le_moteur_n_ecrit_que_en_memoire(tmp_path, monkeypatch):
    """Le pendant dynamique du test statique ci-dessus : générer ne doit toucher aucun
    fichier."""
    avant = {p for p in tmp_path.rglob("*")}
    monkeypatch.chdir(tmp_path)
    MoteurFactice().generer(Requete(prompt="x", graine=1))
    assert {p for p in tmp_path.rglob("*")} == avant


def test_les_poids_ne_telechargent_rien_par_defaut(tmp_path):
    """`auto=False` par défaut — un téléchargement de 12 Go se demande, il ne se subit pas."""
    from illustration.poids import PoidsIntrouvable, assurer_poids

    with pytest.raises(PoidsIntrouvable) as echec:
        assurer_poids(tmp_path / "modele.gguf", url="http://exemple.invalide/x.gguf")
    assert "PAS téléchargés automatiquement" in str(echec.value)


def test_un_telechargement_demande_sans_url_le_dit(tmp_path):
    """Aucune URL n'est codée en dur : la licence des POIDS se vérifie à la source primaire."""
    from illustration.poids import PoidsIntrouvable, assurer_poids

    with pytest.raises(PoidsIntrouvable) as echec:
        assurer_poids(tmp_path / "modele.gguf", url="", auto=True)
    assert "licence" in str(echec.value)
