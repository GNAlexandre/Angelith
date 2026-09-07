# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Alexandre Tournel

"""Étape 0.1 du `PLAN-27` : le chiffre, et la tranche d'interface qu'il impose.

Ces tests ne mesurent rien — la mesure a été faite par les lots 24 à 26 et elle est publiée
avec ses dénominateurs. Ils vérifient que **le code lit son propre tableau**, ce qui est la
seule chose qu'un test puisse faire ici : le jour où la carte change, on ajoute une ligne à
`MESURES` et le verdict suit sans qu'aucune ligne d'interface ait à être relue.
"""
from illustration import attente


def test_les_trois_tranches_du_tableau_du_plan():
    assert attente.tranche(4.0) == attente.A_LA_DEMANDE
    assert attente.tranche(10.0) == attente.FILE
    assert attente.tranche(60.0) == attente.FILE
    assert attente.tranche(60.1) == attente.LOT


def test_le_depot_est_dans_la_tranche_run_par_lot():
    """Le verdict de l'étape 0.1, et il n'est pas près de changer : la médiane la plus basse
    jamais relevée sur cette carte est 1,7× le seuil du haut du tableau."""
    assert attente.tranche_du_depot() == attente.LOT
    assert attente.mediane_mesuree() > attente.SEUIL_FILE


def test_chaque_mesure_porte_son_denominateur():
    """`docs/chiffres-de-reference.md` : « un chiffre sans dénominateur n'est pas une mesure,
    c'est une impression ». Un relevé sans échantillon, sans date ou sans source n'a rien à
    faire dans cette table."""
    for mesure in attente.MESURES:
        assert mesure.echantillon >= 1, mesure
        assert mesure.date and mesure.machine and mesure.moteur, mesure
        assert mesure.source.startswith("docs/mesures/"), mesure


def test_la_mediane_est_ponderee_par_l_echantillon():
    """Une moyenne simple des trois nombres ferait dire au pire cas (n = 1) autant qu'à la
    médiane de la série la plus fournie (n = 4)."""
    valeurs = [m.secondes_par_image for m in attente.MESURES]
    assert attente.mediane_mesuree() == 103.7
    assert attente.mediane_mesuree() < sum(valeurs) / len(valeurs)


def test_l_annonce_donne_une_fourchette_et_son_echantillon_jamais_un_temps_unique():
    """Le rapport entre le meilleur et le pire relevé est de 14,7 : une estimation ponctuelle
    serait fausse d'un facteur dix un jour sur deux, et le dépôt a déjà payé cette leçon avec
    `SECONDES_PAR_RELETTRAGE`, qui valait 1,5 s pour un coût réel de 4,0 s."""
    texte = attente.annonce(4)
    assert "entre" in texte and "et" in texte
    assert str(sum(m.echantillon for m in attente.MESURES)) in texte
    assert "bascule VRAM" in texte


def test_la_bascule_n_est_pas_le_poste_dominant_et_c_est_un_resultat():
    """Le plan prévoyait explicitement que la bascule puisse être « le poste le plus long ».
    Sur cette machine elle ne l'est pas : 2,03 s contre 103,7 s, soit 2 %. C'est un résultat
    de mesure, pas une évidence — d'où ce test, qui échouera le jour où l'un des deux bouge."""
    assert attente.BASCULE_SECONDES / attente.mediane_mesuree() < 0.05


def test_le_resume_publie_la_tranche_et_les_seuils():
    lignes = "\n".join(attente.resume())
    assert "Tranche imposée" in lignes
    assert "103.7" in lignes and "1524.0" in lignes and "857.7" in lignes
