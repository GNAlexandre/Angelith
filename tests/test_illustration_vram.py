# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Alexandre Tournel

"""Critère 4 du `PLAN-27` : **l'annulation décharge la VRAM et recharge le LLM. Testé, y
compris sur erreur.**

Les deux opérations coûteuses sont injectées dans `vram.Bascule`, donc tout ce fichier tourne
sans serveur Ollama, sans réseau et sans GPU — c'est-à-dire en CI, là où le critère doit se
vérifier.
"""
import pytest

from illustration import vram


class MoteurTemoin:
    """Un moteur qui dit s'il a rendu la carte, et combien de fois on le lui a demandé."""

    def __init__(self, rend=True, casse=False):
        self.rend, self.casse, self.appels = rend, casse, 0

    def decharger(self):
        self.appels += 1
        if self.casse:
            raise RuntimeError("ComfyUI a segfaulté (violation d'accès 0xC0000005)")
        return self.rend


def _bascule(**champs):
    trace = {"decharges": [], "recharges": []}
    defauts = dict(
        modeles=("yume-27b",),
        decharge=lambda noms: trace["decharges"].append(list(noms)),
        recharge=lambda noms: trace["recharges"].append(list(noms)),
        dire=lambda _m: None,
        horloge=iter_horloge())
    defauts.update(champs)
    return vram.Bascule(**defauts), trace


def iter_horloge():
    """Une horloge qui avance d'une seconde à chaque lecture — assez pour des durées non
    nulles sans qu'aucun test ne dorme."""
    etat = {"t": 0.0}

    def lire():
        etat["t"] += 1.0
        return etat["t"]
    return lire


def test_ouvrir_decharge_le_llm_une_seule_fois_par_run():
    """Sur huit images, un va-et-vient par image coûterait plus que la génération elle-même."""
    bascule, trace = _bascule()
    premier = bascule.ouvrir()
    second = bascule.ouvrir()
    assert trace["decharges"] == [["yume-27b"]]
    assert premier == second > 0


def test_fermer_est_idempotente_le_second_clic_ne_refait_rien():
    """Blindage contre le second Ctrl+C et le second clic : un appel sur sept à `/free` a fait
    segfauter ComfyUI le 2026-08-29, on ne l'envoie pas deux fois."""
    moteur = MoteurTemoin()
    bascule, _ = _bascule(decharger_image=True)
    bascule.ouvrir()
    bascule.fermer(moteur)
    recap = bascule.fermer(moteur)
    assert moteur.appels == 1
    assert "déjà fermée" in recap["motif"]


def test_le_llm_revient_quand_la_carte_est_reellement_libre():
    moteur = MoteurTemoin(rend=True)
    bascule, trace = _bascule(decharger_image=True)
    bascule.ouvrir()
    recap = bascule.fermer(moteur)
    assert recap["image_rendue"] is True
    assert recap["llm_recharge"] is True
    assert trace["recharges"] == [["yume-27b"]]


def test_le_llm_ne_revient_PAS_quand_le_moteur_tient_encore_la_carte():
    """⚠ Le plan écrit « le LLM revient ». Appliqué à la lettre ce serait un DÉFAUT :
    recharger ~17 Go pendant que ComfyUI tient ses ~12 Go est le scénario que toute
    l'architecture refuse. La brique le DIT au lieu de le faire."""
    bascule, trace = _bascule(decharger_image=False)
    bascule.ouvrir()
    recap = bascule.fermer(MoteurTemoin())
    assert recap["llm_recharge"] is False
    assert trace["recharges"] == []
    assert "tient encore la carte" in recap["motif"]


def test_iso_sur_la_configuration_livree():
    """`decharger_image: false` est le défaut : rien ne change par rapport au lot 26."""
    bascule, trace = _bascule()
    bascule.ouvrir()
    bascule.fermer(MoteurTemoin())
    assert trace["recharges"] == []


def test_rien_a_recharger_si_rien_n_a_ete_decharge():
    bascule, trace = _bascule(decharger_llm=False, decharger_image=True)
    bascule.ouvrir()
    recap = bascule.fermer(MoteurTemoin())
    assert trace["decharges"] == [] and trace["recharges"] == []
    assert "n'avait pas été déchargé" in recap["motif"]


def test_un_moteur_qui_plante_ne_fait_pas_echouer_un_run_dont_les_images_sont_ecrites():
    """Le plantage est chez ComfyUI (`model_management.py:model_unload`, ROCm 7.14) ; nous ne
    pouvons pas le corriger, et les images sont déjà écrites et marquées à ce moment-là."""
    bascule, _ = _bascule(decharger_image=True)
    bascule.ouvrir()
    recap = bascule.fermer(MoteurTemoin(casse=True))
    assert recap["image_rendue"] is False
    assert any(cle == "image_rendue_echec" for cle, _ in recap["journal"])


def test_un_dechargement_de_llm_en_echec_ne_leve_pas_non_plus():
    def casse(_noms):
        raise OSError("Ollama ne répond plus")

    bascule, _ = _bascule(decharge=casse)
    assert bascule.ouvrir() == 0.0
    assert bascule.fermer(None)["llm_recharge"] is False


def test_le_journal_dit_ce_qui_s_est_passe_et_pas_seulement_le_resultat():
    bascule, _ = _bascule(decharger_image=True)
    bascule.ouvrir()
    recap = bascule.fermer(MoteurTemoin())
    cles = [cle for cle, _ in recap["journal"]]
    assert cles == ["llm_decharge", "image_rendue", "llm_recharge"]


# ────────────────────  Le même critère, mais sur le vrai orchestrateur  ────────────────────

def test_la_bascule_se_ferme_meme_quand_la_generation_LEVE(tmp_path, monkeypatch):
    """⚠ **C'est le trou que le lot 27 ferme.** `_rendre_la_vram` vivait APRÈS le bloc de
    génération : une exception de moteur sautait par-dessus et laissait 12 Go sur la carte."""
    from illustration import orchestrateur

    fermetures = []

    class BasculeTemoin:
        def ouvrir(self):
            return 0.0

        def fermer(self, moteur):
            fermetures.append(moteur)
            return {"journal": [], "image_rendue": False, "llm_recharge": False}

    monkeypatch.setattr(orchestrateur, "_bascule", lambda *a, **k: BasculeTemoin())

    class MoteurQuiCasse:
        nom = "casse"
        CANAUX_SUPPORTES = frozenset({"prompt"})

        def disponible(self):
            return True

        def generer(self, requete):
            raise RuntimeError("le serveur a fermé la connexion")

    config, projet = _arbre(tmp_path)
    with pytest.raises(RuntimeError, match="fermé la connexion"):
        orchestrateur.phase_image(projet, config, moteur=MoteurQuiCasse(),
                                  reporter=_muet())
    assert len(fermetures) == 1, "la bascule ne s'est pas fermée sur exception"


def test_l_annulation_arrete_entre_deux_images_et_garde_ce_qui_est_ecrit(tmp_path):
    """Un modèle interrompu en plein pas de débruitage laisse le pilote AMD dans l'état
    mesuré à 25 → 18 tok/s. L'arrêt a donc lieu ENTRE deux images, et les images déjà écrites
    sont gardées, marquées, rapportées."""
    from illustration import orchestrateur
    from illustration.moteur import MoteurFactice

    config, projet = _arbre(tmp_path, images=3)
    faites = {"n": 0}

    def annulation():
        faites["n"] += 1
        return faites["n"] > 2                        # on laisse passer deux images

    recap = orchestrateur.phase_image(
        projet, config, moteur=MoteurFactice(canaux=("prompt",)), reporter=_muet(),
        annulation=annulation)
    assert len(recap["images"]) == 2
    assert "annulé à la demande" in recap["arret"]
    for entree in recap["images"]:
        assert entree["image"].is_file() and entree["manifeste"].is_file()


def test_la_progression_traverse_les_trois_phases_pendant_un_vrai_run(tmp_path):
    from illustration import orchestrateur, progression
    from illustration.moteur import MoteurFactice

    config, projet = _arbre(tmp_path, images=1)
    avancement = progression.Progression()
    orchestrateur.phase_image(projet, config, moteur=MoteurFactice(canaux=("prompt",)),
                              reporter=_muet(), avancement=avancement)
    etat = avancement.etat()
    assert set(etat["secondes"]) == {progression.PREPARATION, progression.BASCULE,
                                     progression.GENERATION}


# ─────────────────────────────────  L'arbre témoin  ─────────────────────────────────

def _muet():
    return type("R", (), {"info": staticmethod(lambda _m: None)})()


def _arbre(tmp_path, images: int = 1):
    """Un projet minimal avec un `requete.yaml` VALIDÉ, sans référence ni bible."""
    from illustration import requete as requete_mod

    (tmp_path / "sources" / "Temoin").mkdir(parents=True)
    (tmp_path / "build" / "Temoin" / "illustrations").mkdir(parents=True)
    config = {"chemins": {"sources": str(tmp_path / "sources"),
                          "build": str(tmp_path / "build")},
              "illustration": {"actif": True, "moteur": "factice"},
              "llm": {}, "modeles": {}}
    doc = requete_mod.vide(modele="factice")
    doc["valide"] = True
    doc["validation"]["par"] = "test"
    doc["validation"]["date"] = "2026-09-02"
    for index in range(images):
        bloc = requete_mod.image_vide(f"temoin-{index + 1}")
        bloc.update({"prompt": f"un portrait numéro {index + 1}", "graine": index})
        doc["images"].append(bloc)
    requete_mod.save(doc, requete_mod.chemin(tmp_path / "build" / "Temoin" / "illustrations"),
                     projet="Temoin", tome="")
    return config, "Temoin"
