# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Alexandre Tournel

"""`illustration/moteur.py` et `illustration/comfyui.py` — les canaux, et leur refus explicite.

Le test central du fichier est `test_un_canal_non_supporte_est_refuse_avec_son_motif` : c'est
le critère 7 bis du `PLAN-24`. Une requête dont le masque aurait été jeté sans un mot
produirait une image plausible et fausse, et personne ne saurait pourquoi — c'est exactement
le défaut que `docs/mesures/webtoon-2026-08-26.md` a dû venir démentir sur un autre sujet.

Le second est `test_la_couleur_du_factice_depend_de_TOUS_les_canaux` : un moteur factice qui
n'écouterait que la graine laisserait passer un vrai moteur qui jette ses canaux, et tous les
tests de bout en bout du lot passeraient quand même.
"""
import io
import json

import pytest

from illustration.comfyui import ComfyIndisponible, MoteurComfyUI
from illustration.moteur import (CANAUX, CanalRefuse, Entite, MoteurFactice, Requete,
                                 verifier_canaux)


def _requete(**champs) -> Requete:
    base = {"prompt": "une jeune femme, cheveux blonds", "graine": 7}
    return Requete(**{**base, **champs})


# ──────────────────────────────  La requête  ──────────────────────────────

def test_la_requete_est_gelee():
    """Une requête se rejoue, elle ne se retouche pas : c'est ce qui rend `valide: true`
    défendable — il porte sur un objet qui ne bouge plus."""
    requete = _requete()
    with pytest.raises(Exception):
        requete.prompt = "autre chose"


def test_avec_produit_une_requete_NOUVELLE():
    requete = _requete()
    autre = requete.avec(graine=8)
    assert requete.graine == 7 and autre.graine == 8
    assert requete.empreinte() != autre.empreinte()


def test_les_canaux_utilises_ignorent_les_scalaires():
    """Dimensions, graine, pas et guidage ne sont pas des canaux : tout moteur les honore,
    il n'y a rien à refuser."""
    assert _requete(prompt="x", largeur=512, pas=4).canaux_utilises() == ("prompt",)


def test_un_champ_blanc_ne_compte_pas_comme_un_canal():
    assert "prompt_negatif" not in _requete(prompt_negatif="   ").canaux_utilises()


def test_les_canaux_sortent_dans_l_ordre_de_priorite():
    requete = _requete(prompt_negatif="flou", references=("media/a.png",),
                       entites=(Entite("un chat", "media/m.png"),), image_controle="c.png")
    assert requete.canaux_utilises() == CANAUX


def test_l_empreinte_change_avec_chaque_canal():
    """Si deux requêtes différentes portaient la même empreinte, le critère de
    reproductibilité de L24.5 ne voudrait rien dire."""
    base = _requete()
    variantes = [base.avec(prompt="autre"), base.avec(prompt_negatif="flou"),
                 base.avec(references=("media/a.png",)),
                 base.avec(entites=(Entite("chat", "m.png"),)),
                 base.avec(image_controle="c.png"), base.avec(graine=8),
                 base.avec(pas=31), base.avec(guidage=5.0), base.avec(largeur=512)]
    empreintes = {v.empreinte() for v in variantes} | {base.empreinte()}
    assert len(empreintes) == len(variantes) + 1


def test_un_aller_retour_par_le_payload_conserve_la_requete():
    """C'est ce que `--rejouer` fait : reconstruire une requête depuis son sidecar."""
    requete = _requete(prompt_negatif="flou", references=("media/a.png", "media/b.png"),
                       entites=(Entite("un chat", "media/m.png"),),
                       image_controle="c.png", guidage=6.5, modele="qwen")
    relue = Requete.depuis_payload(json.loads(json.dumps(requete.payload())))
    assert relue == requete
    assert relue.empreinte() == requete.empreinte()


def test_le_payload_ne_serialise_pas_la_requete_dans_le_prompt():
    """« Le texte reste du texte » : le JSON dans le champ prompt coûterait des tokens sans
    porter de structure lisible par l'encodeur."""
    requete = _requete(references=("media/a.png",))
    assert requete.payload()["prompt"] == requete.prompt
    assert "{" not in requete.payload()["prompt"]


# ─────────────────────────  Le refus explicite des canaux  ─────────────────────────

def test_un_canal_non_supporte_est_refuse_avec_son_motif():
    """Critère 7 bis. Le canal est nommé, le moteur est nommé, le motif est nommé."""
    moteur = MoteurFactice(canaux=("prompt",))
    with pytest.raises(CanalRefuse) as echec:
        moteur.generer(_requete(references=("media/a.png",)))
    assert echec.value.canal == "references"
    assert echec.value.moteur == "factice"
    assert "n'a pas de modèle" in str(echec.value) or echec.value.motif


def test_aucun_canal_n_est_ignore_en_silence():
    """Pour CHAQUE canal : un moteur qui ne le déclare pas lève plutôt que de produire."""
    for canal in CANAUX:
        moteur = MoteurFactice(canaux=[c for c in CANAUX if c != canal])
        requete = {
            "prompt": _requete(prompt="x"),
            "prompt_negatif": _requete(prompt_negatif="flou"),
            "references": _requete(references=("a.png",)),
            "entites": _requete(entites=(Entite("chat", "m.png"),)),
            "image_controle": _requete(image_controle="c.png"),
        }[canal]
        with pytest.raises(CanalRefuse) as echec:
            moteur.generer(requete)
        assert echec.value.canal == canal


def test_verifier_canaux_laisse_passer_ce_qui_est_declare():
    verifier_canaux(MoteurFactice(), _requete(references=("a.png",),
                                              entites=(Entite("chat", "m.png"),)))


# ──────────────────────────────  Le moteur factice  ──────────────────────────────

def test_le_factice_est_deterministe():
    a = MoteurFactice().generer(_requete())
    b = MoteurFactice().generer(_requete())
    assert a.png == b.png


def test_la_couleur_du_factice_depend_de_TOUS_les_canaux():
    """Un factice qui n'écouterait que la graine laisserait passer un moteur qui jette ses
    canaux — et tous les tests de bout en bout du lot passeraient quand même."""
    moteur = MoteurFactice()
    base = moteur.generer(_requete()).png
    for variante in (_requete(prompt="autre"), _requete(references=("a.png",)),
                     _requete(entites=(Entite("chat", "m.png"),)),
                     _requete(image_controle="c.png"), _requete(graine=8)):
        assert moteur.generer(variante).png != base, variante


def test_le_factice_dit_qu_il_est_factice():
    """Une image de test qui traînerait ne doit pas pouvoir passer pour une vraie."""
    provenance = MoteurFactice().generer(_requete()).provenance
    assert provenance["moteur"] == "factice"
    assert "FACTICE" in provenance["avertissement"]


# ──────────────────────────────  Le client ComfyUI  ──────────────────────────────

class _TransportFactice:
    """Un ComfyUI de papier : il met en file, il répond à l'historique, il rend une image."""

    def __init__(self, *, echec=None, images=None, retards=0) -> None:
        self.echec, self.retards = echec, retards
        self.images = images if images is not None else [
            {"filename": "sortie_00001_.png", "subfolder": "", "type": "output"}]
        self.envoye = None
        self.libere = None
        self.appels_historique = 0
        self.journal_demande = False
        self.televersees = []

    def get_json(self, chemin):
        if chemin == "/system_stats":
            return {"system": {"comfyui_version": "0.0-factice"}}
        if chemin == "/internal/logs/raw":
            # ⚠ Ce doublon joue un serveur qui **n'expose pas** cette route (lot 28) : le
            # client doit alors archiver « journal indisponible » et non échouer. Une trace
            # qui manque ne fait jamais échouer un run dont l'image est produite.
            self.journal_demande = True
            return {}
        self.appels_historique += 1
        if self.appels_historique <= self.retards:
            return {}
        entree = {"outputs": {"9": {"images": self.images}}}
        if self.echec:
            entree = {"status": {"status_str": "error", "messages": [self.echec]}}
        return {chemin.rsplit("/", 1)[-1]: entree}

    def post_json(self, chemin, charge):
        if chemin == "/free":
            self.libere = charge
            return {}
        self.envoye = charge
        return {"prompt_id": "abc-123"}

    def get_bytes(self, chemin, parametres):
        return b"\x89PNG\r\n\x1a\n" + parametres["filename"].encode()

    def post_fichier(self, chemin, nom, octets, champs):
        self.televersees.append((chemin, nom, len(octets), dict(champs)))
        return {"name": nom, "subfolder": champs.get("subfolder", ""), "type": "input"}


def _workflow(tmp_path, contenu: dict, *, commentaire=None):
    """Écrit un workflow au format API.

    ⚠ Chaque nœud reçoit un `class_type` s'il n'en a pas : un nœud du format API en porte
    TOUJOURS un, et c'est à ça que le client reconnaît un nœud d'un commentaire. Des
    fixtures sans `class_type` ont masqué ce détail jusqu'au premier appel réel."""
    graphe = {cle: ({"class_type": "Factice", **valeur} if "class_type" not in valeur
                    else valeur)
              for cle, valeur in contenu.items()}
    if commentaire is not None:
        graphe["_commentaire"] = commentaire
    chemin = tmp_path / "workflow.json"
    chemin.write_text(json.dumps(graphe), encoding="utf-8")
    return chemin


def test_les_canaux_du_comfy_sont_LUS_dans_le_graphe(tmp_path):
    """La propriété qu'aucun graphe codé en dur n'aurait : ce que le moteur sait honorer est
    ce que le workflow de l'utilisateur porte."""
    chemin = _workflow(tmp_path, {"3": {"inputs": {"text": "%prompt%", "seed": "%graine%"}}})
    moteur = MoteurComfyUI(chemin, transport=_TransportFactice())
    assert moteur.CANAUX_SUPPORTES == frozenset({"prompt"})
    assert "references" in moteur.MOTIFS and "%reference_1%" in moteur.MOTIFS["references"]


def test_un_canal_absent_du_workflow_est_refuse_avant_toute_seconde_de_GPU(tmp_path):
    chemin = _workflow(tmp_path, {"3": {"inputs": {"text": "%prompt%"}}})
    transport = _TransportFactice()
    moteur = MoteurComfyUI(chemin, transport=transport)
    with pytest.raises(CanalRefuse) as echec:
        moteur.generer(_requete(references=("media/a.png",)))
    assert echec.value.canal == "references"
    assert transport.envoye is None, "le graphe a été envoyé malgré le refus"


def test_un_marqueur_seul_prend_le_TYPE_de_sa_valeur(tmp_path):
    """`"%graine%"` doit devenir l'entier 42, pas la chaîne « 42 » : ComfyUI refuserait la
    chaîne dans un champ numérique."""
    chemin = _workflow(tmp_path, {"3": {"inputs": {"seed": "%graine%", "steps": "%pas%",
                                                   "text": "%prompt%",
                                                   "note": "graine %graine%"}}})
    transport = _TransportFactice()
    MoteurComfyUI(chemin, transport=transport).generer(_requete(graine=42, pas=12))
    entrees = transport.envoye["prompt"]["3"]["inputs"]
    assert entrees["seed"] == 42 and isinstance(entrees["seed"], int)
    assert entrees["steps"] == 12
    assert entrees["note"] == "graine 42"


def test_les_references_sont_TELEVERSEES_et_non_passees_par_chemin(tmp_path):
    """Mesuré le 2026-08-29 contre un vrai ComfyUI : `LoadImage` refuse un chemin absolu avec
    « Invalid image file ». Il ne résout ses images que sous son propre dossier `input/`, donc
    il faut les lui **donner** — et le nom qu'il rend est ce qui part dans le graphe.

    ⚠ Conséquence assumée et dite : une copie de l'extrait atterrit chez ComfyUI. La frontière
    d'Angelith couvre SES écritures, pas celles d'un programme tiers."""
    from illustration.comfyui import SOUS_DOSSIER

    (tmp_path / "media").mkdir()
    (tmp_path / "media" / "a.png").write_bytes(b"\x89PNG\r\n\x1a\nfaux")
    chemin = _workflow(tmp_path, {"3": {"inputs": {"image": "%reference_1%",
                                                   "text": "%prompt%"}}})
    transport = _TransportFactice()
    moteur = MoteurComfyUI(chemin, transport=transport, dossier_tome=tmp_path)
    moteur.generer(_requete(references=("media/a.png",)))

    assert transport.televersees, "la référence doit être téléversée"
    endpoint, nom, _, champs = transport.televersees[0]
    assert endpoint == "/upload/image" and champs["subfolder"] == SOUS_DOSSIER
    envoye = transport.envoye["prompt"]["3"]["inputs"]["image"]
    assert envoye == f"{SOUS_DOSSIER}/{nom}"
    assert str(tmp_path) not in envoye, "aucun chemin absolu ne doit partir dans le graphe"


def test_un_meme_fichier_n_est_televerse_qu_UNE_fois(tmp_path):
    """Un run de onze images qui partagent leurs références ne les renvoie pas onze fois, et
    le nom porte l'empreinte du contenu : deux runs de même requête envoient le même graphe —
    ce que la reproductibilité de L24.5 exige."""
    (tmp_path / "media").mkdir()
    (tmp_path / "media" / "a.png").write_bytes(b"\x89PNG\r\n\x1a\nfaux")
    chemin = _workflow(tmp_path, {"3": {"inputs": {"image": "%reference_1%",
                                                   "text": "%prompt%"}}})
    transport = _TransportFactice()
    moteur = MoteurComfyUI(chemin, transport=transport, dossier_tome=tmp_path)
    moteur.generer(_requete(references=("media/a.png",)))
    premier = transport.envoye["prompt"]["3"]["inputs"]["image"]
    moteur.generer(_requete(references=("media/a.png",)))
    assert len(transport.televersees) == 1
    assert transport.envoye["prompt"]["3"]["inputs"]["image"] == premier


def test_une_reference_absente_du_disque_est_nommee(tmp_path):
    chemin = _workflow(tmp_path, {"3": {"inputs": {"image": "%reference_1%",
                                                   "text": "%prompt%"}}})
    moteur = MoteurComfyUI(chemin, transport=_TransportFactice(), dossier_tome=tmp_path)
    with pytest.raises(ComfyIndisponible, match="introuvable"):
        moteur.generer(_requete(references=("media/absent.png",)))


def test_les_noeuds_de_reference_INUTILISES_sont_elagues(tmp_path):
    """Sans ça, un graphe à trois références ne saurait recevoir qu'exactement trois
    références : `%reference_2%` resterait tel quel dans un `LoadImage`, et ComfyUI refuserait
    le graphe entier pour un fichier nommé « %reference_2% ».

    C'est l'élagage qui rend le **balayage du nombre de références** possible avec UN seul
    workflow — sinon il en faudrait trois, qui divergeraient au premier réglage changé."""
    (tmp_path / "media").mkdir()
    (tmp_path / "media" / "a.png").write_bytes(b"\x89PNG\r\n\x1a\nfaux")
    chemin = _workflow(tmp_path, {
        "10": {"inputs": {"image": "%reference_1%"}},
        "11": {"inputs": {"image": "%reference_2%"}},
        "12": {"inputs": {"image": "%reference_3%"}},
        "20": {"inputs": {"text": "%prompt%", "image1": ["10", 0], "image2": ["11", 0],
                          "image3": ["12", 0]}}})
    transport = _TransportFactice()
    moteur = MoteurComfyUI(chemin, transport=transport, dossier_tome=tmp_path)
    moteur.generer(_requete(references=("media/a.png",)))

    envoye = transport.envoye["prompt"]
    assert set(envoye) == {"10", "20"}, envoye
    assert set(envoye["20"]["inputs"]) == {"text", "image1"}, envoye["20"]["inputs"]


def test_l_elagage_ne_touche_pas_un_graphe_complet(tmp_path):
    (tmp_path / "a.png").write_bytes(b"\x89PNG\r\n\x1a\nfaux")
    (tmp_path / "b.png").write_bytes(b"\x89PNG\r\n\x1a\nautre")
    chemin = _workflow(tmp_path, {
        "10": {"inputs": {"image": "%reference_1%"}},
        "11": {"inputs": {"image": "%reference_2%"}},
        "20": {"inputs": {"text": "%prompt%", "image1": ["10", 0], "image2": ["11", 0]}}})
    transport = _TransportFactice()
    moteur = MoteurComfyUI(chemin, transport=transport, dossier_tome=tmp_path)
    moteur.generer(_requete(references=("a.png", "b.png")))
    envoye = transport.envoye["prompt"]
    assert set(envoye) == {"10", "11", "20"}
    assert set(envoye["20"]["inputs"]) == {"text", "image1", "image2"}


def test_une_cle_de_COMMENTAIRE_ne_part_pas_dans_le_graphe(tmp_path):
    """Défaut réel, trouvé au premier appel contre un vrai ComfyUI le 2026-08-29.

    ComfyUI itère sur TOUTES les clés racine et appelle `.get('_meta')` sur chacune : une
    clé de commentaire dont la valeur est une liste le fait tomber en `AttributeError`,
    renvoyée au client en « HTTP 500 Internal Server Error » sans autre indication.

    Le dépôt vit de fichiers commentés — on garde donc le droit de commenter un workflow
    écrit à la main, et c'est le client qui nettoie juste avant l'envoi."""
    chemin = _workflow(tmp_path, {"3": {"inputs": {"text": "%prompt%"}}},
                       commentaire=["une ligne de prose", "une autre"])
    transport = _TransportFactice()
    moteur = MoteurComfyUI(chemin, transport=transport)
    assert moteur.CANAUX_SUPPORTES == frozenset({"prompt"})
    moteur.generer(_requete())
    assert list(transport.envoye["prompt"]) == ["3"], transport.envoye["prompt"]


def test_un_COMMENTAIRE_qui_cite_un_marqueur_ne_declare_PAS_le_canal(tmp_path):
    """Défaut réel, trouvé le 2026-08-29 en relisant les deux workflows livrés.

    `_canaux_du_graphe` lisait le TEXTE BRUT du fichier. Un commentaire qui cite
    « %reference_1% » — précisément pour expliquer que ce workflow ne le porte PAS — faisait
    déclarer le canal supporté. Le moteur aurait alors accepté une requête à références et les
    aurait **ignorées en silence** : exactement le défaut que tout ce dispositif existe pour
    empêcher, réintroduit par une ligne de documentation."""
    chemin = _workflow(
        tmp_path, {"3": {"inputs": {"text": "%prompt%"}}},
        commentaire=["Ce workflow ne porte NI %reference_1% NI %masque_1% NI %image_controle% :",
                     "le moteur refusera donc ces canaux."])
    moteur = MoteurComfyUI(chemin, transport=_TransportFactice())
    assert moteur.CANAUX_SUPPORTES == frozenset({"prompt"})
    with pytest.raises(CanalRefuse) as echec:
        moteur.generer(_requete(references=("a.png",)))
    assert echec.value.canal == "references"


#: Ce que CHAQUE workflow livré déclare honorer. La table est explicite, workflow par
#: workflow, plutôt qu'une règle commune : un graphe qui se mettrait à déclarer un canal qu'il
#: n'honore pas produirait une image plausible et fausse, et c'est exactement ce que le
#: critère 7 bis du `PLAN-24` existe pour empêcher.
CANAUX_ATTENDUS = {
    "qwen-image-2512.api.json": {"prompt", "prompt_negatif"},
    "qwen-image-2512-lightning.api.json": {"prompt", "prompt_negatif"},
    # Le graphe de la VOIE A du PLAN-25 : lui seul porte %reference_N%.
    "qwen-image-edit-2511.api.json": {"prompt", "prompt_negatif", "references"},
    # ⚑ CANDIDAT du PLAN-30 (2026-09-03) : jamais exécuté, poids non installé. Il est ici pour
    # la même raison que les autres — un graphe qui déclarerait un canal qu'il n'honore pas
    # produirait une image plausible et fausse, et « candidat » n'exempte de rien.
    "qwen-image-edit-2511-controle.api.json": {"prompt", "prompt_negatif", "references",
                                               "image_controle"},
}

#: Les canaux qu'un workflow livré **EXIGE**, workflow par workflow — `PLAN-30` L30.1.
#:
#: ⚠ **Vide partout sauf sur le candidat, et c'est la règle, pas un état de fait.** Un graphe
#: qui exige un canal n'est pas un graphe du chemin nominal : il ne dégrade pas, donc il ne peut
#: pas être le défaut de quiconque. Ce test est ce qui empêche qu'un jour `config.yaml` en
#: désigne un sans que personne ne s'en aperçoive.
EXIGES_ATTENDUS = {
    "qwen-image-2512.api.json": (),
    "qwen-image-2512-lightning.api.json": (),
    "qwen-image-edit-2511.api.json": (),
    "qwen-image-edit-2511-controle.api.json": ("image_controle",),
}


def test_les_workflows_LIVRES_declarent_exactement_ce_qu_ils_honorent():
    from pathlib import Path

    racine = Path(__file__).resolve().parent.parent / "illustration" / "workflows"
    livres = sorted(racine.glob("*.api.json"))
    assert livres, "aucun workflow livré — le test ne prouverait rien"
    assert {c.name for c in livres} == set(CANAUX_ATTENDUS), "un workflow livré non déclaré ici"
    for chemin in livres:
        moteur = MoteurComfyUI(chemin, transport=_TransportFactice())
        attendus = CANAUX_ATTENDUS[chemin.name]
        assert moteur.CANAUX_SUPPORTES == frozenset(attendus), chemin.name
        assert set(moteur.MOTIFS) == {"prompt", "prompt_negatif", "references", "entites",
                                      "image_controle"} - attendus, chemin.name
        assert moteur.CANAUX_EXIGES == EXIGES_ATTENDUS[chemin.name], chemin.name


def test_le_graphe_d_edition_cable_bien_TROIS_references():
    """`REFERENCES_MAX` n'est pas un réglage de prudence : c'est ce que le nœud
    `TextEncodeQwenImageEditPlus` expose (`image1`, `image2`, `image3`). Si le graphe et la
    constante divergeaient, le balayage demanderait une quatrième référence que rien ne
    recevrait."""
    import json as _json
    from pathlib import Path

    from illustration.identite import REFERENCES_MAX

    chemin = (Path(__file__).resolve().parent.parent / "illustration" / "workflows"
              / "qwen-image-edit-2511.api.json")
    texte = _json.dumps(_json.loads(chemin.read_text(encoding="utf-8")))
    portes = [i for i in range(1, 10) if f"%reference_{i}%" in texte]
    assert portes == list(range(1, REFERENCES_MAX + 1)), portes


def test_un_workflow_qui_n_est_QUE_de_la_prose_est_refuse(tmp_path):
    chemin = tmp_path / "workflow.json"
    chemin.write_text(json.dumps({"_commentaire": ["rien que du texte"]}), encoding="utf-8")
    with pytest.raises(ComfyIndisponible) as echec:
        MoteurComfyUI(chemin, transport=_TransportFactice())
    assert "aucun nœud" in str(echec.value)


def test_le_corps_d_une_erreur_HTTP_est_relaye(tmp_path):
    """« HTTP Error 500 » tout seul a coûté un aller-retour dans les logs du serveur. Le
    corps de la réponse porte, sur un 400, le `node_errors` qui nomme le nœud fautif."""
    import urllib.error

    from illustration.comfyui import Transport

    transport = Transport("http://exemple.invalide", 5)

    def _casse(requete, timeout=None):
        raise urllib.error.HTTPError(
            "http://exemple.invalide/prompt", 400, "Bad Request", {},
            io.BytesIO(b'{"node_errors": {"7": "steps doit etre un entier"}}'))

    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr("illustration.comfyui.urllib.request.urlopen", _casse)
    try:
        with pytest.raises(ComfyIndisponible) as echec:
            transport.get_json("/prompt")
    finally:
        monkeypatch.undo()
    assert "400" in str(echec.value)
    assert "steps doit etre un entier" in str(echec.value)


def test_le_workflow_de_l_utilisateur_n_est_jamais_reecrit(tmp_path):
    chemin = _workflow(tmp_path, {"3": {"inputs": {"text": "%prompt%"}}})
    avant = chemin.read_bytes()
    MoteurComfyUI(chemin, transport=_TransportFactice()).generer(_requete())
    assert chemin.read_bytes() == avant


def test_le_sondage_attend_que_l_historique_apparaisse(tmp_path):
    chemin = _workflow(tmp_path, {"3": {"inputs": {"text": "%prompt%"}}})
    transport = _TransportFactice(retards=3)
    moteur = MoteurComfyUI(chemin, transport=transport, attente=lambda _: None)
    sortie = moteur.generer(_requete())
    assert transport.appels_historique == 4
    assert sortie.png.startswith(b"\x89PNG")


def test_une_erreur_du_serveur_est_relayee_et_non_avalee(tmp_path):
    chemin = _workflow(tmp_path, {"3": {"inputs": {"text": "%prompt%"}}})
    moteur = MoteurComfyUI(chemin, transport=_TransportFactice(echec="nœud introuvable"),
                           attente=lambda _: None)
    with pytest.raises(ComfyIndisponible) as echec:
        moteur.generer(_requete())
    assert "nœud introuvable" in str(echec.value)


def test_un_workflow_sans_image_produite_le_dit(tmp_path):
    chemin = _workflow(tmp_path, {"3": {"inputs": {"text": "%prompt%"}}})
    moteur = MoteurComfyUI(chemin, transport=_TransportFactice(images=[]),
                           attente=lambda _: None)
    with pytest.raises(ComfyIndisponible) as echec:
        moteur.generer(_requete())
    assert "SaveImage" in str(echec.value)


def test_un_export_au_mauvais_format_est_nomme(tmp_path):
    """Un export « normal » de ComfyUI n'est pas un format API, et le message doit le dire :
    c'est l'erreur que tout le monde fait une fois."""
    chemin = tmp_path / "workflow.json"
    chemin.write_text("[1, 2, 3]", encoding="utf-8")
    with pytest.raises(ComfyIndisponible) as echec:
        MoteurComfyUI(chemin, transport=_TransportFactice())
    assert "FORMAT API" in str(echec.value)


def test_le_moteur_rend_la_VRAM_par_l_endpoint_free(tmp_path):
    """La SECONDE moitié de la bascule. Elle manquait jusqu'au 2026-08-29 : après un run,
    12 083 Mio restaient occupés par le transformeur, et un `run.py` lancé derrière trouvait
    la carte prise."""
    chemin = _workflow(tmp_path, {"3": {"inputs": {"text": "%prompt%"}}})
    transport = _TransportFactice()
    moteur = MoteurComfyUI(chemin, transport=transport)
    assert moteur.decharger() is True
    assert transport.libere == {"unload_models": True, "free_memory": True}


def test_un_dechargement_qui_echoue_ne_fait_pas_tomber_le_run(tmp_path):
    """Best-effort, comme `ollama_unload` : le run est terminé, les images sont écrites et
    marquées. Lever ici perdrait un travail déjà fait pour une VRAM non rendue."""
    class _Muet(_TransportFactice):
        def post_json(self, chemin, charge):
            if chemin == "/free":
                raise OSError("serveur parti")
            return super().post_json(chemin, charge)

    chemin = _workflow(tmp_path, {"3": {"inputs": {"text": "%prompt%"}}})
    assert MoteurComfyUI(chemin, transport=_Muet()).decharger() is False


def test_decharger_moteur_tolere_un_moteur_qui_ne_sait_pas():
    """Un moteur sans `decharger` — ou le factice, qui n'a rien chargé — ne doit pas casser
    la fin de run."""
    from illustration.moteur import decharger_moteur

    class _Nu:
        nom = "nu"

    assert decharger_moteur(_Nu()) is False
    assert decharger_moteur(MoteurFactice()) is False


def test_sans_workflow_le_moteur_n_est_pas_disponible():
    assert MoteurComfyUI(None, transport=_TransportFactice()).disponible() is False


def test_le_graphe_dit_QUELS_MODELES_il_charge(tmp_path):
    """Défaut de provenance trouvé le 2026-08-29 : `requete.yaml` porte un champ `modele`
    écrit par la phase 1 d'après la configuration d'alors, et la phase 2 le recopiait dans le
    sidecar sans le confronter à rien. Un manifeste qui se trompe de modèle est pire qu'un
    manifeste sans modèle : il a l'air vérifiable."""

    chemin = _workflow(tmp_path, {
        "1": {"class_type": "UnetLoaderGGUF", "inputs": {"unet_name": "edit-Q4_1.gguf"}},
        "2": {"class_type": "LoraLoaderModelOnly", "inputs": {"lora_name": "lightning.safetensors"}},
        "3": {"class_type": "VAELoader", "inputs": {"vae_name": "vae.safetensors"}},
        "4": {"inputs": {"text": "%prompt%"}},
        "5": {"class_type": "SaveImage", "inputs": {"filename_prefix": "angelith"}}})
    transport = _TransportFactice()
    moteur = MoteurComfyUI(chemin, transport=transport)
    sortie = moteur.generer(_requete())
    assert sortie.provenance["modeles"] == ["edit-Q4_1.gguf", "lightning.safetensors",
                                            "vae.safetensors"]
    # ⚠ `filename_prefix` n'est PAS un modèle : le confondre écrirait un nom de sortie dans la
    # provenance.
    assert "angelith" not in sortie.provenance["modeles"]


def test_les_modeles_du_graphe_LIVRE_sont_ceux_qu_on_croit():
    """Si le graphe d'édition se mettait à charger le transformeur texte-vers-image, le
    sidecar de chaque image le dirait — et ce test échouerait d'abord."""
    from pathlib import Path

    from illustration.comfyui import modeles_du_graphe

    racine = Path(__file__).resolve().parent.parent / "illustration" / "workflows"
    graphe = json.loads((racine / "qwen-image-edit-2511.api.json").read_text(encoding="utf-8"))
    modeles = modeles_du_graphe({c: v for c, v in graphe.items() if isinstance(v, dict)
                                 and "class_type" in v})
    assert any("edit-2511" in m for m in modeles), modeles
    assert not any("2512" in m and "edit" not in m for m in modeles), modeles
