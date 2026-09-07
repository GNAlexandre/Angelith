# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Alexandre Tournel

"""L27.2 — la progression distingue **préparation / bascule / génération**, avec le temps réel
de chacune, et elle n'invente jamais un pourcentage.

⚠ Aucun `sleep` : l'horloge est injectée, donc chaque durée se vérifie à la milliseconde.
Un test qui dormirait une seconde par phase coûterait plus cher que tout le reste du fichier
et vérifierait moins.
"""
import pytest

from illustration import progression as prog


class Horloge:
    """Une horloge qu'on avance à la main."""

    def __init__(self):
        self.t = 0.0

    def __call__(self):
        return self.t

    def avancer(self, secondes):
        self.t += secondes
        return self.t


def test_les_trois_phases_ont_chacune_leur_temps_reel():
    horloge = Horloge()
    p = prog.Progression(horloge=horloge)
    p.demarrer(prog.PREPARATION)
    horloge.avancer(91.4)
    p.demarrer(prog.BASCULE)
    horloge.avancer(2.0)
    p.demarrer(prog.GENERATION)
    horloge.avancer(414.8)
    p.terminer()

    assert p.secondes(prog.PREPARATION) == pytest.approx(91.4)
    assert p.secondes(prog.BASCULE) == pytest.approx(2.0)
    assert p.secondes(prog.GENERATION) == pytest.approx(414.8)
    assert p.total_secondes() == pytest.approx(508.2)


def test_ouvrir_une_phase_ferme_la_precedente():
    """Sans quoi la somme des trois durées dépasserait le temps écoulé — le genre de chiffre
    qui décrédibilise tout un rapport."""
    horloge = Horloge()
    p = prog.Progression(horloge=horloge)
    p.demarrer(prog.PREPARATION)
    horloge.avancer(10.0)
    p.demarrer(prog.GENERATION)
    horloge.avancer(10.0)
    assert p.total_secondes() == pytest.approx(20.0)


def test_une_phase_en_cours_rend_le_temps_ECOULE_pas_zero():
    horloge = Horloge()
    p = prog.Progression(horloge=horloge)
    p.demarrer(prog.GENERATION)
    horloge.avancer(180.0)
    assert p.secondes(prog.GENERATION) == pytest.approx(180.0)


def test_la_fraction_est_None_tant_qu_aucune_image_n_est_terminee():
    """`None` n'est pas « zéro pour cent » : c'est « je ne sais pas », et l'interface le
    traduit par une barre indéterminée. Les confondre afficherait 0 % pendant les cent
    premières secondes d'un run qui avance très bien."""
    p = prog.Progression(total_images=8)
    p.demarrer(prog.GENERATION)
    assert p.fraction() is None
    p.image_terminee("aya")
    assert p.fraction() == pytest.approx(1 / 8)


def test_la_fraction_compte_les_images_jamais_le_temps():
    p = prog.Progression(total_images=4, horloge=Horloge())
    p.demarrer(prog.GENERATION)
    for _ in range(4):
        p.image_terminee()
    assert p.fraction() == 1.0
    p.image_terminee()                     # une image de plus ne dépasse pas 100 %
    assert p.fraction() == 1.0


def test_le_libelle_dit_ce_qui_occupe_la_carte():
    """Une barre bloquée qui dit pourquoi n'est plus une barre bloquée."""
    p = prog.Progression()
    p.demarrer(prog.BASCULE)
    assert "bascule de modèle" in p.libelle()
    assert "coexistent jamais" in p.libelle()


def test_l_annulation_se_dit_avant_que_la_phase_se_termine():
    """Sinon l'utilisateur reclique, et un second clic ne doit pas envoyer un second `/free`
    à un serveur dont un appel sur sept a déjà fait segfauter ComfyUI."""
    p = prog.Progression(total_images=8)
    p.demarrer(prog.GENERATION)
    p.demander_l_annulation()
    assert "annulation demandée" in p.libelle()
    assert "ne reclique pas" in p.libelle()
    assert p.etat()["annulation_demandee"] is True


def test_le_resume_ne_liste_pas_une_phase_qui_n_a_pas_eu_lieu():
    """Écrire « bascule 0,0 s » quand la bascule n'a pas eu lieu (`decharger_llm: false`)
    laisserait croire qu'elle est gratuite alors qu'elle n'a pas été payée."""
    horloge = Horloge()
    p = prog.Progression(horloge=horloge)
    p.demarrer(prog.GENERATION)
    horloge.avancer(103.7)
    p.terminer()
    assert "bascule" not in p.resume()
    assert "génération (image) 103.7 s" in p.resume()


def test_une_phase_inconnue_leve_plutot_que_de_s_ajouter():
    with pytest.raises(ValueError, match="phase inconnue"):
        prog.Progression().demarrer("inference")


def test_l_etat_est_plat_et_traversable_par_un_signal():
    """Un dictionnaire de scalaires : rien qui oblige un signal Qt à transporter un objet."""
    p = prog.Progression(total_images=2)
    p.demarrer(prog.PREPARATION)
    etat = p.etat()
    assert set(etat) == {"phase", "libelle", "fraction", "images_faites", "total_images",
                         "annulation_demandee", "secondes"}
    assert all(isinstance(v, (int, float)) for v in etat["secondes"].values())
