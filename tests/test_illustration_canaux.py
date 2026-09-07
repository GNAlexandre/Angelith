# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Alexandre Tournel

"""`PLAN-30` — le canal candidat, la copie non marquée, et le taux d'échec de `/free`.

Le critère 8 du plan exige que tout ce lot se teste **sans serveur, sans poids et sans GPU**.
C'est ce que fait ce fichier : le graphe candidat est un JSON, la validation lit un
`/object_info` écrit à la main, et le protocole de `/free` reçoit ses deux opérations en
injection.

⚠ **Ce que ces tests NE prouvent PAS, et il faut le lire avant de s'y fier.** Ils vérifient que
le dépôt *refuse au bon moment* et *déclare ce qu'il fait*. Ils ne disent rien de l'apport du
canal — qui n'est pas mesuré au 2026-09-03 —, rien de la compatibilité du `MODEL_PATCH` avec le
transformeur d'édition quantifié, et rien du taux d'échec réel de `/free`. Ces trois choses
demandent le PC principal, et `docs/mesures/canaux-2026-09-03.md` les nomme une par une.
"""
import json
from pathlib import Path

import pytest

from illustration import validation as validation_mod
from illustration import vram as vram_mod
from illustration.comfyui import MARQUEURS_OPTIONNELS, MoteurComfyUI
from illustration.moteur import (CanalExige, CanalRefuse, Requete, verifier_canaux,
                                 verifier_canaux_exiges)
from tests.test_illustration_validation import GRAPHE, _releve

WORKFLOWS = Path(__file__).resolve().parents[1] / "illustration" / "workflows"
CANDIDAT = WORKFLOWS / "qwen-image-edit-2511-controle.api.json"


class _TransportMuet:
    """Un transport qui **compte** ce qu'on lui demande. Aucun appel n'est attendu ici : tout
    l'intérêt du refus est qu'il arrive avant la première requête."""

    def __init__(self):
        self.appels = []

    def get_json(self, route, params=None):
        self.appels.append(("GET", route))
        return {}

    def post_json(self, route, charge):
        self.appels.append(("POST", route))
        return {}

    def get_bytes(self, route, params=None):
        self.appels.append(("GET", route))
        return b""


def _moteur(chemin, dossier=None):
    return MoteurComfyUI(chemin, transport=_TransportMuet(), dossier_tome=dossier)


# ═══════════════  L30.1 — le graphe candidat se déclare, et n'est le défaut de personne  ═══

def test_le_graphe_candidat_dit_ce_qu_il_est_et_ce_qu_il_faut_installer():
    """Le bloc `_candidat` porte les quatre choses que l'étape 0.2 du plan demande d'écrire
    AVANT de télécharger : le motif, le poids avec sa source et sa licence datée, le canal
    exigé, et le seuil d'abandon."""
    moteur = _moteur(CANDIDAT)
    candidat = moteur.candidat
    assert candidat["plan"] == "PLAN-30 L30.1"
    assert candidat["exige"] == ["image_controle"]
    poids = candidat["poids"][0]
    assert poids["licence"] == "Apache-2.0"
    assert poids["licence_verifiee_le"] == "2026-09-03"
    # ⚠ Le critère 2 exige l'empreinte du fichier RÉCUPÉRÉ : il n'a pas été téléchargé, et le
    # champ le DIT plutôt que de porter une valeur inventée ou un blanc.
    assert "NON RELEVE" in poids["sha256"]
    # « lowvram patches » est le seuil d'abandon du critère 3, écrit d'avance.
    assert "lowvram" in candidat["abandon"]
    # Aucun nœud tiers : c'est l'argument qui a fait préférer ce canal à EliGen (étape 0.2).
    assert candidat["noeuds_tiers"] == []


def test_config_yaml_ne_designe_PAS_le_graphe_candidat():
    """⚠ **Le critère 4 du plan : le canal est livré DÉSARMÉ.** Un candidat qui deviendrait le
    défaut ferait échouer chaque run sur une machine sans le poids."""
    import yaml

    racine = Path(__file__).resolve().parents[1]
    config = yaml.safe_load((racine / "config.yaml").read_text(encoding="utf-8"))
    assert config["illustration"]["comfyui"]["workflow"] != str(
        CANDIDAT.relative_to(racine)).replace("\\", "/")
    assert "controle" not in config["illustration"]["comfyui"]["workflow"]


def test_le_bloc_candidat_ne_part_JAMAIS_au_serveur(tmp_path):
    """`_candidat` est une clé racine sans `class_type` : `_sans_commentaires` la retire, comme
    n'importe quel commentaire. ComfyUI itère sur toutes les clés racine et tomberait dessus."""
    (tmp_path / "c.png").write_bytes(b"x")
    (tmp_path / "r.png").write_bytes(b"y")
    moteur = _moteur(CANDIDAT, dossier=tmp_path)
    graphe, _ = moteur.graphe_substitue(
        Requete(prompt="p", references=("r.png",), image_controle="c.png"), televerser=False)
    assert "_candidat" not in graphe
    assert "_commentaire" not in graphe
    assert all("class_type" in n for n in graphe.values())


# ═══  L30.1 — le premier graphe du dépôt qui NE DÉGRADE PAS, et le refus qui va avec  ═══

def test_le_canal_exige_est_refuse_AVANT_la_premiere_requete():
    """⚠ La réciproque de `CanalRefuse`. Le nœud de contrôle est **en série sur le chemin du
    modèle** : l'élaguer priverait le `KSampler` de son modèle, et ComfyUI répondrait sur une
    entrée manquante sans dire laquelle. Le refus arrive donc ici, avec le champ à remplir."""
    moteur = _moteur(CANDIDAT)
    with pytest.raises(CanalExige) as echec:
        moteur.generer(Requete(prompt="p", references=("a.png",)))
    assert echec.value.canal == "image_controle"
    assert "image_de_controle" in str(echec.value)
    assert "requete.yaml" in str(echec.value)
    # Le point du test : zéro requête. Pas un `/prompt`, pas même un `GET`.
    assert moteur.transport.appels == []


def test_un_graphe_ORDINAIRE_n_exige_rien():
    """⚠ **La règle, pas un état de fait** : un graphe qui exige un canal ne peut pas être le
    défaut de quiconque. Les trois graphes qui ont tourné n'exigent rien."""
    for nom in ("qwen-image-2512.api.json", "qwen-image-2512-lightning.api.json",
                "qwen-image-edit-2511.api.json"):
        moteur = _moteur(WORKFLOWS / nom)
        assert moteur.CANAUX_EXIGES == (), nom
        assert moteur.candidat == {}, nom
        # Et le refus habituel tient toujours : ces graphes ne portent pas %image_controle%.
        with pytest.raises(CanalRefuse):
            verifier_canaux(moteur, Requete(prompt="p", image_controle="x.png"))


def test_verifier_canaux_exiges_laisse_passer_une_requete_complete():
    moteur = _moteur(CANDIDAT)
    verifier_canaux_exiges(moteur, Requete(prompt="p", image_controle="croquis.png"))


# ═══  Le défaut silencieux trouvé en chemin : %image_controle% n'était pas élagable  ═══

def test_image_controle_est_un_marqueur_ELAGABLE(tmp_path):
    """⚠ **C'était un défaut, et il ne pouvait pas se voir avant ce lot.** L'élagage ne
    connaissait que les marqueurs INDEXÉS (`%reference_2%`), parce qu'aucun graphe du dépôt ne
    portait `%image_controle%`. Sans le correctif, une requête sans image de contrôle aurait
    envoyé `LoadImage(image: "")` à ComfyUI — donc une erreur d'exécution, après le chargement
    des poids."""
    assert "%image_controle%" in MARQUEURS_OPTIONNELS
    assert "%prompt%" not in MARQUEURS_OPTIONNELS       # ne doit JAMAIS y entrer
    (tmp_path / "r.png").write_bytes(b"y")
    moteur = _moteur(CANDIDAT, dossier=tmp_path)
    graphe, _ = moteur.graphe_substitue(Requete(prompt="p", references=("r.png",)),
                                        televerser=False)
    charges = [n for n in graphe.values()
               if n.get("class_type") == "LoadImage" and n["inputs"].get("image") == ""]
    assert charges == [], "un LoadImage part avec un nom d'image VIDE"


def test_le_graphe_d_edition_livre_reste_ISO(tmp_path):
    """Le correctif d'élagage ne devait toucher **aucun** graphe qui marchait. Quatorze nœuds
    au fichier, douze après élagage d'une requête à une référence — comme avant le lot 30."""
    (tmp_path / "r.png").write_bytes(b"y")
    moteur = _moteur(WORKFLOWS / "qwen-image-edit-2511.api.json", dossier=tmp_path)
    graphe, _ = moteur.graphe_substitue(Requete(prompt="p", references=("r.png",)),
                                        televerser=False)
    assert len(graphe) == 12
    assert "13" not in graphe            # ce graphe n'a pas de nœud de contrôle
    assert graphe["31"]["inputs"]["model"] == ["3", 0]


# ═══════════  L30.1 — le validateur connaît le candidat, et ne crie pas dessus  ═══════════

def test_un_candidat_RETROGRADE_ses_noeuds_absents_en_reserves(tmp_path):
    """⚠ Sans cette rétrogradation, `tools/comfy.py --valider` sans argument passerait en ROUGE
    sur toute machine du monde : le dépôt livre un graphe dont le poids n'est installé nulle
    part. Un diagnostic qui crie sur un état normal cesse d'être lu."""
    graphe = {**GRAPHE, "_candidat": {"motif": "poids non installé au 2026-09-03",
                                      "canal": "image_controle", "plan": "PLAN-30 L30.1"},
              "1": {"class_type": "NoeudQuiNExistePas", "inputs": {}}}
    chemin = tmp_path / "candidat.api.json"
    chemin.write_text(json.dumps(graphe), encoding="utf-8")
    rapport = validation_mod.valider(chemin, releve=_releve(), pas=4, guidage=1.0)
    assert rapport.ok, "un candidat non installé ne doit pas faire échouer le diagnostic"
    reserves = {c.code for c in rapport.reserves}
    assert "noeud_absent" in reserves
    # ⚠ Le constat n'est PAS effacé : c'est la liste de courses de qui veut l'installer.
    retrograde = [c for c in rapport.reserves if c.code == "noeud_absent"][0]
    assert "NoeudQuiNExistePas" in retrograde.quoi
    assert "CANDIDAT non installé" in retrograde.correction
    assert "poids non installé au 2026-09-03" in retrograde.correction


def test_un_graphe_ORDINAIRE_refuse_toujours_un_noeud_absent(tmp_path):
    """La contre-épreuve : sans bloc `_candidat`, le même graphe est refusé. Sinon la
    rétrogradation serait un interrupteur qui éteint la validation."""
    graphe = {**GRAPHE, "1": {"class_type": "NoeudQuiNExistePas", "inputs": {}}}
    chemin = tmp_path / "ordinaire.api.json"
    chemin.write_text(json.dumps(graphe), encoding="utf-8")
    rapport = validation_mod.valider(chemin, releve=_releve(), pas=4, guidage=1.0)
    assert not rapport.ok
    assert [c.code for c in rapport.refus] == ["noeud_absent"]


def test_un_candidat_MAL_FORME_reste_refuse(tmp_path):
    """⚠ Seuls les codes de `CODES_CANDIDAT` sont rétrogradés. Un guidage incohérent avec une
    LoRA distillée ne vient pas de la machine : il vient du fichier, et il reste un refus."""
    graphe = {**GRAPHE, "_candidat": {"motif": "peu importe"}}
    chemin = tmp_path / "brule.api.json"
    chemin.write_text(json.dumps(graphe), encoding="utf-8")
    rapport = validation_mod.valider(chemin, releve=_releve(), pas=4, guidage=4.0)
    assert [c.code for c in rapport.refus] == ["guidage_incoherent"]


def test_le_rapport_AFFICHE_la_source_et_la_licence_du_poids():
    """Le critère 2 demande que la licence soit publiée avec sa date. Elle l'est là où on la
    lit au bon moment : dans le rapport de validation, pas seulement dans un document."""
    rapport = validation_mod.valider(CANDIDAT, releve=None, pas=4, guidage=1.0)
    texte = "\n".join(rapport.lignes())
    assert "GRAPHE CANDIDAT" in texte
    assert "Apache-2.0" in texte and "2026-09-03" in texte
    assert "huggingface.co/Comfy-Org/Qwen-Image-DiffSynth-ControlNets" in texte
    assert "canal_exige" in {c.code for c in rapport.constats}


# ═══════════  L30.3 — vérification 6 : où atterrit la copie non marquée  ═══════════

def test_saveimage_pose_une_RESERVE_qui_nomme_la_copie_non_marquee(tmp_path):
    """⚠ Une réserve, pas un refus : c'est l'état livré et il est assumé. Ce qui manquait,
    c'est qu'il soit **dit au moment de valider**."""
    chemin = tmp_path / "w.api.json"
    chemin.write_text(json.dumps(GRAPHE), encoding="utf-8")
    rapport = validation_mod.valider(chemin, releve=_releve(), pas=4, guidage=1.0)
    assert rapport.ok
    reserve = [c for c in rapport.reserves if c.code == "copie_non_marquee"][0]
    assert "tEXt" in reserve.quoi and "output/" in reserve.quoi
    assert "PreviewImage" in reserve.correction


def test_previewimage_ne_pose_AUCUNE_reserve(tmp_path):
    """`PreviewImage` écrit dans `temp/`, que ComfyUI vide à son redémarrage — et ce client le
    récupère sans changer une ligne, parce qu'il transmet à `/view` le `type` que l'historique
    donne."""
    graphe = {**GRAPHE, "9": {"class_type": "PreviewImage", "inputs": {"images": ["8", 0]}}}
    chemin = tmp_path / "w.api.json"
    chemin.write_text(json.dumps(graphe), encoding="utf-8")
    rapport = validation_mod.valider(chemin, releve=_releve(), pas=4, guidage=1.0)
    assert rapport.ok
    assert "copie_non_marquee" not in {c.code for c in rapport.constats}
    assert "temp/" in rapport.verifications["sortie du graphe"]


def test_saveimagewebsocket_est_REFUSE_avec_son_motif_mecanique(tmp_path):
    """⚠ **C'est la réponse du critère 6 du plan, et elle est écrite dans le code.** Le README
    des workflows conseillait `SaveImageWebsocket` pour éviter la copie non marquée : ce client
    ne sait mécaniquement pas le lire — il récupère l'image par `/history` puis `/view`, et ce
    nœud ne publie rien dans l'historique. Le graphe s'exécuterait, occuperait la carte
    plusieurs minutes, puis échouerait sur « n'a produit aucune image »."""
    graphe = {**GRAPHE, "9": {"class_type": "SaveImageWebsocket",
                              "inputs": {"images": ["8", 0]}}}
    chemin = tmp_path / "w.api.json"
    chemin.write_text(json.dumps(graphe), encoding="utf-8")
    rapport = validation_mod.valider(chemin, releve=None, pas=4, guidage=1.0)
    refus = [c for c in rapport.refus if c.code == "sortie_websocket"][0]
    assert "/history" in refus.quoi
    assert "PreviewImage" in refus.correction


def test_un_graphe_SANS_noeud_de_sortie_est_refuse(tmp_path):
    """ComfyUI l'exécuterait et ne publierait rien dans `/history` : le client échoue déjà sur
    « n'a produit aucune image », mais après avoir payé le chargement des poids."""
    graphe = {c: v for c, v in GRAPHE.items() if v.get("class_type") != "SaveImage"}
    chemin = tmp_path / "w.api.json"
    chemin.write_text(json.dumps(graphe), encoding="utf-8")
    rapport = validation_mod.valider(chemin, releve=None, pas=4, guidage=1.0)
    assert [c.code for c in rapport.refus] == ["sortie_absente"]


def test_le_client_recupere_une_image_de_TYPE_temp():
    """La preuve que `PreviewImage` ne demande aucun changement : le client passe à `/view` le
    `type` que l'historique lui donne. C'est une lecture du code, rendue exécutable."""
    vus = []

    class _Transport:
        def post_json(self, route, charge):
            return {"prompt_id": "abc"}

        def get_json(self, route, params=None):
            return {"abc": {"status": {"status_str": "success"},
                            "outputs": {"9": {"images": [{"filename": "x.png",
                                                          "subfolder": "", "type": "temp"}]}}}}

        def get_bytes(self, route, params=None):
            vus.append(dict(params or {}))
            return b"PNG"

    moteur = MoteurComfyUI(WORKFLOWS / "qwen-image-2512-lightning.api.json",
                           transport=_Transport(), plancher_secondes=0.0)
    sortie = moteur.generer(Requete(prompt="p"))
    assert sortie.png == b"PNG"
    assert vus and vus[0]["type"] == "temp"


# ═══════════  L30.4 — le taux d'échec de `/free`, avec son dénominateur  ═══════════

def test_vingt_appels_sans_panne_donnent_un_denominateur():
    releve = vram_mod.mesurer_free(liberer=lambda: True, vivant=lambda: True,
                                   repetitions=20, version="0.34.2", dire=lambda _: None)
    assert (releve.appels, releve.pannes, releve.taux) == (20, 0, 0.0)
    assert releve.complet
    assert "0.34.2" in releve.phrase()


def test_un_serveur_qui_MEURT_arrete_le_releve_et_dit_a_quel_rang():
    """⚠ **Le défaut que ce protocole évite.** Le mode d'échec mesuré n'est pas « l'appel rend
    une erreur », c'est « ComfyUI meurt ». Une boucle qui ne sonderait pas entre deux appels
    compterait dix-sept succès imaginaires après le troisième, et publierait « 1 sur 20 » là où
    la vérité est « 1 sur 3, puis plus rien »."""
    etat = {"vivant": True, "n": 0}

    def liberer():
        etat["n"] += 1
        if etat["n"] == 3:
            etat["vivant"] = False
        return True

    releve = vram_mod.mesurer_free(liberer=liberer, vivant=lambda: etat["vivant"],
                                   repetitions=20, version="0.34.2", dire=lambda _: None)
    assert releve.arret_au == 3
    assert releve.appels == 3 and releve.pannes == 1
    assert not releve.complet
    # ⚠ Et il ne relance PAS ComfyUI : le plan l'interdit. Trois appels, pas vingt.
    assert etat["n"] == 3
    assert "ARRÊT au 3e appel" in releve.phrase()
    assert "s'additionnent" in releve.phrase()


def test_un_releve_trop_court_ne_conclut_PAS():
    """Sept n'est pas un dénominateur, et le relevé le dit lui-même plutôt que de laisser un
    lecteur en tirer un taux."""
    releve = vram_mod.mesurer_free(liberer=lambda: True, vivant=lambda: True,
                                   repetitions=7, version="0.34.2", dire=lambda _: None)
    assert not releve.complet
    assert str(vram_mod.APPELS_DE_REFERENCE) in releve.phrase()


def test_un_appel_qui_LEVE_ne_fait_pas_echouer_le_releve():
    """Best-effort, comme partout dans ce module : un serveur qui ne répond pas ne doit pas
    faire remonter une exception jusqu'à l'appelant."""
    releve = vram_mod.mesurer_free(liberer=lambda: (_ for _ in ()).throw(OSError("boum")),
                                   vivant=lambda: True, repetitions=2, dire=lambda _: None)
    assert releve.appels == 2 and releve.pannes == 0
    assert any(cle == "appel_en_echec" for _, cle, _ in releve.journal)
    # ⚠ **Comptés à part, mais DITS.** Une erreur HTTP n'est pas le segfault : les additionner
    # produirait un taux qui ne se compare plus au « 1 sur 7 » du 2026-08-29. Les taire ferait
    # croire à deux appels réussis.
    assert releve.appels_en_echec == 2
    assert "en ERREUR sans tuer le serveur" in releve.phrase()


def test_decharger_image_reste_DESARME_dans_le_config_livre():
    """⚠ **Critère 7 : armé ou désarmé D'APRÈS LE CHIFFRE.** Le chiffre n'a pas pu être repris
    au 2026-09-03 — la session tournait sans serveur —, donc rien ne change. Ce test existe
    pour qu'un futur armement soit un geste conscient et non un effet de bord."""
    import yaml

    racine = Path(__file__).resolve().parents[1]
    config = yaml.safe_load((racine / "config.yaml").read_text(encoding="utf-8"))
    assert config["illustration"]["vram"]["decharger_image"] is False



# ═══  Le CÂBLAGE entre `--liberer-vram` et le protocole — défaut relevé le 2026-09-03  ═══
#
# ⚠ **Pourquoi ces deux tests existent, et ce qu'ils disent du lot 30.** Les quatre tests
# ci-dessus couvrent `vram.mesurer_free`, c'est-à-dire la LOGIQUE qui compte. Rien ne couvrait
# la COMMANDE qui l'actionne — `grep -rn "liberer_vram" tests/` ne rendait rien —, et c'est
# précisément là que le défaut vivait : `run_illustration.py` construisait `MoteurComfyUI` sans
# son premier argument positionnel. `--liberer-vram` mourait donc sur un `TypeError` avant le
# premier `POST /free`, depuis sa naissance en 2.24.0, et aucun test ne pouvait le voir. Il a
# fallu la première exécution contre un vrai serveur pour l'apercevoir
# (`docs/mesures/canaux-2026-09-03.md` §12.1). Un mécanisme testé derrière une commande cassée
# vaut zéro.

def _config_comfy():
    """La configuration du dépôt, telle qu'elle est livrée — c'est ce que la commande lit."""
    import yaml

    racine = Path(__file__).resolve().parents[1]
    return yaml.safe_load((racine / "config.yaml").read_text(encoding="utf-8"))


def test_liberer_vram_ATTEINT_le_protocole_sans_lever(monkeypatch):
    """⚠ **Le test qui aurait échoué avant la 2.24.1.** Il ne vérifie aucun taux : il vérifie
    que la commande arrive jusqu'à `mesurer_free`. Avant le correctif elle levait un
    `TypeError` deux lignes plus haut, et le taux n'avait donc jamais pu exister."""
    import run_illustration
    from illustration import sonde as sonde_mod
    from illustration import vram as vram_reel

    monkeypatch.setattr(sonde_mod, "depuis_config", lambda *_a, **_k: _releve())
    monkeypatch.setattr(MoteurComfyUI, "decharger", lambda self: True)
    vus = {}
    reel = vram_reel.mesurer_free          # ⚠ capturé AVANT la pose de l'espion

    def espion(*, liberer, vivant, repetitions, version=None, dire=None):
        vus["repetitions"], vus["version"] = repetitions, version
        return reel(liberer=liberer, vivant=vivant, repetitions=repetitions,
                    version=version, dire=lambda _m: None)

    monkeypatch.setattr(vram_reel, "mesurer_free", espion)
    assert run_illustration._liberer_vram(_config_comfy(), repetitions=3) is True
    # ⚠ Les répétitions demandées arrivent telles quelles : un dénominateur qui se perd en
    # route serait pire qu'un dénominateur absent.
    assert vus["repetitions"] == 3


def test_rendre_la_carte_ne_demande_AUCUN_graphe(monkeypatch, tmp_path):
    """⚠ **Le corollaire, et c'est lui qui fixe la forme du correctif.** `decharger()` ne touche
    qu'au transport : `POST /free`. Construire le moteur avec le graphe configuré ferait échouer
    « rends-moi la VRAM » parce qu'un fichier JSON est mal formé — le pire moment pour refuser.
    Le moteur se construit donc avec `workflow=None`, et ce test le tient."""
    import run_illustration
    from illustration import sonde as sonde_mod

    config = _config_comfy()
    casse = tmp_path / "casse.api.json"
    casse.write_text("{ ceci n'est pas du JSON", encoding="utf-8")
    config["illustration"]["comfyui"]["workflow"] = str(casse)
    monkeypatch.setattr(sonde_mod, "depuis_config", lambda *_a, **_k: _releve())
    monkeypatch.setattr(MoteurComfyUI, "decharger", lambda self: True)
    assert run_illustration._liberer_vram(config, repetitions=1) is True


# ═══════════  L30.2 — l'axe `canal` du banc, fermé par défaut  ═══════════

def test_l_axe_canal_est_FERME_par_defaut():
    """⚠ Le critère d'iso-comportement : un balayage lancé sans `--controle` produit exactement
    les mêmes configurations, sous exactement les mêmes noms, qu'avant le lot 30. Deux séries
    mesurées à six mois d'écart doivent rester comparables fichier par fichier."""
    banc = pytest.importorskip("tools.banc_identite")
    noms = [c.nom for c in banc.configurations()]
    assert noms == ["nombre_references-r1-p4-g1", "nombre_references-r2-p4-g1",
                    "nombre_references-r3-p4-g1", "force-r2-p6-g1", "force-r2-p8-g1"]
    assert all(c.controle == "" for c in banc.configurations())


def test_l_axe_canal_ajoute_UN_point_et_le_nomme():
    """⚠ **Un seul point, et il coûte une image.** Le plan ne demande pas de balayer la force
    du canal : il demande de le comparer à son absence, sur les mêmes descripteurs et le même
    juge. Le point « sans » existe déjà — c'est `nombre_references` à 2."""
    banc = pytest.importorskip("tools.banc_identite")
    avec = banc.configurations(controle="croquis.png")
    assert len(avec) == 6
    canal = [c for c in avec if c.axe == "canal"]
    assert len(canal) == 1
    assert canal[0].controle == "croquis.png"
    assert canal[0].nom.endswith("-controle")
    assert canal[0].references == 2 and canal[0].pas == 4


def test_une_image_de_controle_ABSENTE_est_dite_avant_tout_chargement(tmp_path):
    """⚠ Même discipline que `--decors`, et pour la même raison : découvrir « fichier
    introuvable » après le déchargement du LLM et le chargement de 12,8 Go de poids coûte
    exactement ce que le lot 28 a passé son temps à supprimer."""
    banc = pytest.importorskip("tools.banc_identite")

    class _Args:
        controle = str(tmp_path / "jamais.png")

    with pytest.raises(SystemExit) as echec:
        banc._controle_demande(_Args())
    assert "n'existe pas" in str(echec.value)
    assert "FOURNIE par toi" in str(echec.value)


def test_le_HELP_du_banc_ne_plante_pas():
    """⚠ **Défaut réel, attrapé en relisant le diff du lot 30.** Le texte d'aide de
    `--controle` citait le marqueur littéral, pourcents compris. `argparse` **formate** les
    aides avec `%` : le `%i` du marqueur y devenait une conversion d'entier, et
    `banc_identite.py --help` mourait sur un `TypeError` — sur toutes les options, pas
    seulement celle-là.

    Le test est volontairement large : il rend `--help` de l'outil entier, donc il attrape le
    prochain `%` écrit dans n'importe quelle aide de ce fichier."""
    import sys as _sys

    banc = pytest.importorskip("tools.banc_identite")
    argv = list(_sys.argv)
    try:
        _sys.argv = ["banc_identite.py", "--help"]
        # `--help` sort en SystemExit(0) APRÈS avoir formaté l'aide ; c'est le formatage qui
        # levait un TypeError, donc une sortie propre est la preuve que le défaut est corrigé.
        with pytest.raises(SystemExit) as sortie:
            banc.main()
        assert sortie.value.code in (0, None)
    finally:
        _sys.argv = argv


def test_le_devis_compte_l_image_du_canal():
    """L29.5 : le coût se publie AVANT de lancer. Un devis qui ignorerait l'axe `canal`
    sous-estimerait la carte d'une image par personnage."""
    banc = pytest.importorskip("tools.banc_identite")
    sans = "\n".join(banc.section_devis(1, 10))
    avec = "\n".join(banc.section_devis(1, 10, controle="croquis.png"))
    assert sans != avec
