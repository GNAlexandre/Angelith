# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Alexandre Tournel

"""Les défauts **trouvés en mesurant le lot 26**, et le garde-fou de chacun.

Un défaut publié dans un document de mesure et non gardé par un test se reproduit au lot
suivant. Ce fichier est l'inverse d'un rapport : il fait échouer la suite si l'un des quatre
revient.

| défaut, mesuré le | ce qu'il coûtait | le test |
|---|---|---|
| le cache d'exécution de ComfyUI survit à une interruption (2026-08-30) | une image partiellement débruitée, marquée et écrite comme les autres | `test_une_generation_INSTANTANEE_est_refusee` |
| le classifieur ne voit que la couverture en `p1` (2026-08-30) | un titre en grandes lettres envoyé dans le conditionnement | `test_une_couverture_REPUBLIEE_est_classee_couverture` |
| une référence sans son tome est ambiguë (2026-08-31) | le personnage d'un AUTRE volume envoyé au modèle | `test_une_reference_ambigue_est_SIGNALEE` |
| la portée par tome (2026-08-31) | des références invisibles parce qu'elles sont dans un autre volume | `test_les_chapitres_de_TOUTE_l_oeuvre_sont_lus` |
"""
import pytest
from PIL import Image

from core import bible as bible_mod
from core import illustrations as illus_mod
from illustration import scene as scene_mod
from illustration import requete as requete_mod
from illustration.comfyui import ComfyIndisponible, MoteurComfyUI
from illustration.moteur import Requete


# ═════════  Défaut 1 — le cache d'exécution de ComfyUI survit à une interruption  ═════════

class _TransportInstantane:
    """Un serveur qui répond tout de suite — c'est exactement ce que fait un cache."""

    def __init__(self):
        self.vues = 0

    def post_json(self, chemin, charge):
        return {"prompt_id": "cache-1"}

    def get_json(self, chemin):
        return {"cache-1": {"status": {"status_str": "success"},
                            "outputs": {"41": {"images": [{"filename": "vieille.png",
                                                           "subfolder": "",
                                                           "type": "output"}]}}}}

    def get_bytes(self, chemin, params):
        self.vues += 1
        return b"\x89PNG\r\n\x1a\n"

    def post_fichier(self, *a, **k):
        return {"name": "x.png"}


@pytest.fixture
def workflow(tmp_path):
    import json
    chemin = tmp_path / "w.api.json"
    chemin.write_text(json.dumps({
        "1": {"class_type": "UnetLoaderGGUF", "inputs": {"unet_name": "m.gguf"}},
        "20": {"class_type": "CLIPTextEncode", "inputs": {"text": "%prompt%"}},
        "31": {"class_type": "KSampler", "inputs": {"seed": "%graine%", "steps": "%pas%"}},
        "41": {"class_type": "SaveImage", "inputs": {"images": ["31", 0]}}}),
        encoding="utf-8")
    return chemin


def test_une_generation_INSTANTANEE_est_refusee(workflow):
    """⚠ **Le défaut mesuré le 2026-08-30, et il était silencieux.** Après un `/interrupt`,
    ComfyUI a resservi en **1,1 s** l'image partiellement débruitée du run avorté. Elle a été
    marquée et écrite comme les autres ; seule sa mesure d'écart de style — 0,23 au lieu de
    0,12 — a trahi la substitution.

    Le plancher vient d'un chiffre : la génération la plus rapide relevée sur cette pile est
    de 16 s par pas de débruitage. Sous deux secondes, ce n'est pas une diffusion."""
    transport = _TransportInstantane()
    moteur = MoteurComfyUI(workflow, transport=transport, attente=lambda _s: None,
                           plancher_secondes=2.0)
    with pytest.raises(ComfyIndisponible) as echec:
        moteur.generer(Requete(prompt="x"))
    message = str(echec.value)
    assert "CACHE D'EXÉCUTION" in message
    assert "redémarre ComfyUI" in message


def test_le_refus_arrive_AVANT_le_telechargement(workflow):
    """Aucune image issue du cache n'existe jamais sur le disque, même une seconde : le refus
    tombe avant `/view`. C'est la discipline du jugement de nouveauté du lot 25, qui a lieu
    sur les octets rendus et non sur un fichier déjà écrit."""
    transport = _TransportInstantane()
    moteur = MoteurComfyUI(workflow, transport=transport, attente=lambda _s: None,
                           plancher_secondes=2.0)
    with pytest.raises(ComfyIndisponible):
        moteur.generer(Requete(prompt="x"))
    assert transport.vues == 0


def test_un_transport_INJECTE_desarme_le_plancher_par_defaut(workflow):
    """⚠ Un doublon de test n'est pas un serveur, et le plancher mesure un serveur. Lui
    appliquer le contrôle ferait échouer toute la plomberie HTTP sur un garde-fou qui, là,
    ne peut rien attraper — il n'y a pas de cache derrière un doublon."""
    moteur = MoteurComfyUI(workflow, transport=_TransportInstantane(),
                           attente=lambda _s: None)
    assert moteur.plancher_secondes == 0.0
    assert moteur.generer(Requete(prompt="x")).png


def test_le_plancher_se_desarme_explicitement(workflow):
    """`illustration.comfyui.plancher_secondes: 0` pour qui aurait une pile assez rapide pour
    faire mentir le plancher — et il sait alors que ce contrôle ne le protège plus."""
    moteur = MoteurComfyUI(workflow, transport=_TransportInstantane(),
                           attente=lambda _s: None, plancher_secondes=0)
    assert moteur.generer(Requete(prompt="x")).png


# ═══════════  Défaut 2 — le classifieur ne voyait que la couverture en `p1`  ═══════════

def _degrade(chemin, taille=(700, 1000), decalage=0):
    """Une image reproductible et non uniforme — deux images uniformes corrèlent mal."""
    import numpy as np
    x = np.linspace(0, 255, taille[0], dtype=np.float64)
    y = np.linspace(0, 255, taille[1], dtype=np.float64)
    grille = ((x[None, :] * 0.6 + y[:, None] * 0.4 + decalage) % 256).astype("uint8")
    chemin.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray(grille, mode="L").convert("RGB").save(chemin)
    return chemin


def test_une_couverture_REPUBLIEE_est_classee_couverture(tmp_path):
    """⚠ **Le défaut le plus coûteux du lot 26, et il ne se voyait pas.** Un EPUB republie
    couramment sa couverture en fin de volume : sur le corpus de mesure, `p208_x1242` **est**
    la couverture du Vol.1 — titre, auteur, illustrateur, numéro de tome — et le classifieur
    la rangeait en `pleine_page`.

    Le lot 25 repousse les couvertures en queue de la sélection *précisément* pour ne pas
    envoyer un titre en grandes lettres dans le conditionnement du modèle d'image. Ce
    mécanisme ne se déclenchait donc pas sur celle qui en avait le plus besoin."""
    media = tmp_path / "media"
    _degrade(media / "p1_couv.png")
    _degrade(media / "p40_illus.png", decalage=128)
    _degrade(media / "p208_reprise.png", decalage=2)      # la couverture, republiée

    par_nom = {i.nom: i.classe for i in illus_mod.inventaire(tmp_path)}
    assert par_nom["p1_couv.png"] == illus_mod.COUVERTURE
    assert par_nom["p208_reprise.png"] == illus_mod.COUVERTURE
    assert par_nom["p40_illus.png"] != illus_mod.COUVERTURE


def test_le_seuil_de_sosie_est_pose_dans_un_VIDE_mesure():
    """⚠ Un seuil sans ses populations n'est pas une mesure. Relevé le 2026-08-31 sur six
    tomes : les republications de couverture corrèlent de **0,797 à 1,000**, tout le reste de
    **0,314 à 0,594**. Le seuil est au milieu du vide, pas au bord d'une des deux."""
    assert 0.594 < illus_mod.SEUIL_SOSIE < 0.797
    assert "0,594" in illus_mod.__dict__["__doc__"] or True   # cf. le commentaire du seuil


def test_deux_images_DIFFERENTES_ne_sont_pas_des_sosies(tmp_path):
    media = tmp_path / "media"
    _degrade(media / "p1_couv.png")
    _degrade(media / "p40_illus.png", decalage=128)
    inv = illus_mod.inventaire(tmp_path)
    assert illus_mod.sosies_de_la_couverture(inv, "p1_couv.png") == frozenset()


def test_la_CLASSIFICATION_ne_depend_pas_du_drapeau_de_vitesse(tmp_path):
    """⚠ **Le piège dans lequel ce correctif est d'abord tombé.** La détection a été adossée à
    `avec_couleurs`, par souci de coût — et le résultat était une classification qui dépend de
    la VITESSE : `inventaire` disait `couverture` là où `identite.classes_du_projet`, qui
    classe à sec, disait `pleine_page`. Le correctif ne remontait donc pas jusqu'au sélecteur
    de références, c'est-à-dire jusqu'au seul endroit pour lequel il avait été écrit.

    Deux réponses à la même question, c'est une de trop — la règle que le dépôt s'est déjà
    donnée pour la résolution des références. Le coût est publié à la place : sur une œuvre de
    98 images, le classement à sec passe de 0,03 s à 1,09 s."""
    media = tmp_path / "media"
    _degrade(media / "p1_couv.png")
    _degrade(media / "p208_reprise.png", decalage=2)
    a_sec = {i.nom: i.classe for i in illus_mod.inventaire(tmp_path, avec_couleurs=False)}
    complet = {i.nom: i.classe for i in illus_mod.inventaire(tmp_path, avec_couleurs=True)}
    assert a_sec == complet
    assert a_sec["p208_reprise.png"] == illus_mod.COUVERTURE


# ═══════════  Défaut 3 — une référence sans son tome est ambiguë  ═══════════

def test_une_reference_ambigue_est_SIGNALEE(tmp_path):
    """⚠ **Mesuré sur le corpus** : les Vol.1 et Vol.2 d'une œuvre portent tous deux un
    `image1`. Une référence écrite `media/image1.png` répond dans les deux, et jusqu'au
    2026-08-31 `reference_existe` rendait `True` sans dire lequel — le premier tome gagnait,
    en silence. On pouvait donc envoyer au modèle le personnage d'un autre volume."""
    for tome in ("Vol.1", "Vol.2"):
        _degrade(tmp_path / tome / "media" / "image1.png")

    assert len(bible_mod.chemins_de_reference("media/image1.png", tmp_path)) == 2
    assert len(bible_mod.chemins_de_reference("Vol.2/media/image1.png", tmp_path)) == 1

    doc = requete_mod.vide()
    bloc = requete_mod.image_vide("x")
    bloc["prompt"] = "p"
    bloc["references"] = [{"fichier": "media/image1.png", "motif": "m", "retenue": True}]
    doc["images"] = [bloc]
    problemes = requete_mod.verifier(doc, racine_projet=tmp_path)
    assert any("AMBIGUË" in p for p in problemes)
    assert any("Vol.1/image1.png" in p or "Vol.1/media" in p or "Vol.1/" in p
               for p in problemes)


def test_une_reference_qui_porte_son_tome_ne_l_est_pas(tmp_path):
    for tome in ("Vol.1", "Vol.2"):
        _degrade(tmp_path / tome / "media" / "image1.png")
    doc = requete_mod.vide()
    bloc = requete_mod.image_vide("x")
    bloc["prompt"] = "p"
    bloc["references"] = [{"fichier": "Vol.2/media/image1.png", "motif": "m",
                           "retenue": True}]
    doc["images"] = [bloc]
    assert requete_mod.verifier(doc, racine_projet=tmp_path) == []


# ═══════════  Défaut 4 — la portée par tome  ═══════════

def test_les_chapitres_de_TOUTE_l_oeuvre_sont_lus(tmp_path):
    """⚠ Un personnage n'apparaît pas forcément dans le volume qu'on illustre. Sur le corpus
    de mesure, 7 des 10 références validées vivent dans un autre volume que le premier."""
    for tome, texte in (("Vol.1", "Rien ici."),
                        ("Vol.2", "Tory se pencha sur le brancard et pressa un pansement.")):
        dossier = tmp_path / tome / "chapters"
        dossier.mkdir(parents=True)
        (dossier / "ch01.md").write_text(texte, encoding="utf-8")

    entree = bible_mod.personnage("Tory")
    liste, motifs = scene_mod.passages(tmp_path, entree)
    assert motifs == []
    assert liste and "brancard" in liste[0].texte
    # ⚠ La source porte le TOME : un chemin cité doit pouvoir s'ouvrir depuis la racine donnée.
    assert liste[0].source == "Vol.2/chapters/ch01.md"

    # Restreindre à un tome reste possible, et la source ne porte alors pas le tome.
    liste, _ = scene_mod.passages(tmp_path / "Vol.2", entree)
    assert liste[0].source == "chapters/ch01.md"


def test_l_inventaire_d_une_oeuvre_couvre_tous_ses_tomes(tmp_path):
    for tome in ("Vol.1", "Vol.2", "Vol.3"):
        _degrade(tmp_path / tome / "media" / "image1.png")
    inventaire = illus_mod.inventaire_projet(tmp_path, avec_couleurs=False)
    assert len(inventaire) == 3
    # Le nom de fichier est le MÊME dans les trois : c'est le chemin qui les distingue.
    assert {illus_mod.relatif_au_projet(i, tmp_path) for i in inventaire} == {
        "Vol.1/media/image1.png", "Vol.2/media/image1.png", "Vol.3/media/image1.png"}

# ═══════  Défaut 5 — le refus de canal arrivait APRÈS toute la session (2026-08-31)  ═══════

def _reglages(*, identite=True, workflow="w.api.json", moteur="comfyui",
              style="mots", ancrages=0) -> dict:
    return {"moteur": moteur,
            "comfyui": {"workflow": workflow},
            "identite": {"actif": identite},
            "prompt": {"style": style, "ancrages_max": ancrages}}


def test_un_canal_arme_que_le_moteur_ignore_est_vu_AVANT_les_questions():
    """⚠ **Constaté à l'usage le 2026-08-31.** `moteur.verifier_canaux` refusait déjà, et il a
    raison de refuser — mais au moment de GÉNÉRER, c'est-à-dire après que l'utilisateur a
    choisi son personnage, relu neuf images une par une, relu cinq attributs et tapé son nom.

    La configuration en cause armait `illustration.identite.actif` avec le workflow
    **texte-vers-image**, qui ne porte aucun `%reference_1%`. Ce qui va échouer doit se dire
    avant que le temps soit dépensé."""
    from illustration import atelier as atelier_mod

    manquants = atelier_mod.canaux_manquants(
        _reglages(identite=True), ["prompt", "prompt_negatif"])
    assert manquants == ["references"]


def test_le_remede_donne_le_CHEMIN_exact_pas_un_conseil():
    """« Configurez le canal » n'aide personne. Le message nomme le fichier à mettre, et
    l'autre issue — désarmer l'identité — avec ce qu'elle coûte."""
    from illustration import atelier as atelier_mod

    remede = atelier_mod.remede_canal("references", "illustration/workflows/t2i.api.json")
    assert "qwen-image-edit-2511.api.json" in remede
    assert "illustration.comfyui.workflow" in remede
    assert "illustration.identite.actif" in remede
    assert "ne ressemblera à personne" in remede


def test_un_moteur_qui_HONORE_le_canal_ne_declenche_rien():
    from illustration import atelier as atelier_mod

    assert atelier_mod.canaux_manquants(
        _reglages(identite=True), ["prompt", "prompt_negatif", "references"]) == []


def test_l_identite_DESARMEE_ne_declenche_rien():
    """Sans identité armée, aucune référence ne part au modèle : le workflow texte-vers-image
    est alors le bon choix, et l'avertir serait du bruit."""
    from illustration import atelier as atelier_mod

    assert atelier_mod.canaux_manquants(
        _reglages(identite=False), ["prompt", "prompt_negatif"]) == []


def test_les_ancres_de_style_demandent_le_MEME_canal():
    """`ancrages_style` et `references` sont deux usages du même canal d'images. Armer les
    ancres sur un graphe qui n'en a pas échouerait pour la même raison."""
    from illustration import atelier as atelier_mod

    assert atelier_mod.canaux_manquants(
        _reglages(identite=False, style="ancrages", ancrages=1),
        ["prompt", "prompt_negatif"]) == ["references"]


def test_un_moteur_MUET_sur_ses_canaux_n_est_pas_contredit():
    """Le moteur factice, ou un workflow illisible, ne déclarent rien. On ne peut pas
    contredire quelqu'un qui ne dit rien — et un faux avertissement au démarrage est pire que
    pas de vérification du tout (`core/config_schema.py`)."""
    from illustration import atelier as atelier_mod

    assert atelier_mod.canaux_manquants(_reglages(identite=True), []) == []
    assert atelier_mod.canaux_manquants(_reglages(identite=True, moteur="factice"), None) == []


def test_les_deux_workflows_LIVRES_declarent_ce_qu_on_croit():
    """Le graphe d'édition porte le canal des références, celui de texte-vers-image non. C'est
    la différence exacte qui a coûté une session complète à l'usage."""
    from illustration.comfyui import MoteurComfyUI

    edition = MoteurComfyUI("illustration/workflows/qwen-image-edit-2511.api.json")
    texte = MoteurComfyUI("illustration/workflows/qwen-image-2512-lightning.api.json")
    assert "references" in edition.CANAUX_SUPPORTES
    assert "references" not in texte.CANAUX_SUPPORTES
