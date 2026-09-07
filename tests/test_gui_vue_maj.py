# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Alexandre Tournel

"""`gui/vue_maj.py` — **quand la fenêtre s'ouvre, et ce qu'elle dit avant le clic**.

## Le défaut que ces tests empêchent, et il est spécifique à ce lot

La vérification passe de désarmée à **armée par défaut**. Ce qui était jusqu'ici une ligne dans
une page « À propos » que personne n'ouvre devient une fenêtre que **tout le monde** verra au
démarrage. Deux dérives sont possibles, et chacune a son test :

1. **ouvrir sur un échec** — au 2026-09-06, le miroir public rend 404 (mesuré : 0,72 s). Si la
   fenêtre s'ouvrait sur « je n'ai pas pu vérifier », ce lot aurait livré une fenêtre d'erreur
   quotidienne à tout le monde et rien d'autre ;
2. **proposer d'installer ce qu'on ne peut pas vérifier** — une release sans
   `SHA256SUMS.txt`, ou une installation depuis les sources. Un installeur qu'on ne peut pas
   vérifier vaut MOINS qu'un lien, parce qu'il aurait l'air vérifié.

## Sans Qt

Règle de couche du dépôt : ce qui décide se teste sans PySide6. Ce fichier n'importe pas Qt.
"""
from __future__ import annotations

import pytest

from core import maj
from gui import vue_maj as vmaj

INSTALLEUR = maj.Asset("Angelith-99.0.0-windows-x64-setup.exe",
                       "https://example.invalid/setup.exe", 306242994)
SOMMES = maj.Asset(maj.NOM_SOMMES, "https://example.invalid/SHA256SUMS.txt", 105)


def _resultat(**kw) -> maj.Resultat:
    base = {"arme": True, "disponible": True, "version": "99.0.0",
            "assets": (INSTALLEUR, SOMMES)}
    base.update(kw)
    return maj.Resultat(**base)


# --------------------------------------------------------------------------- #
#  Quand la fenêtre s'ouvre
# --------------------------------------------------------------------------- #

def test_une_version_plus_recente_ouvre_la_fenetre():
    assert vmaj.doit_proposer(_resultat()) is True


def test_ne_plus_afficher_ferme_la_porte():
    assert vmaj.doit_proposer(_resultat(), {"maj_silencieuse": True}) is False


def test_la_meme_version_n_ouvre_rien():
    assert vmaj.doit_proposer(_resultat(disponible=False)) is False


def test_un_echec_de_verification_n_ouvre_JAMAIS_rien():
    """⚠ **Le test qui compte le plus de ce fichier.** Au 2026-09-06, `GET` sur le miroir rend
    404 : le dépôt public est privé jusqu'à la candidature NLnet. Ouvrir sur un échec ferait de
    ce lot une fenêtre d'erreur quotidienne pour tout le monde."""
    assert vmaj.doit_proposer(maj.Resultat(arme=True, detail="aucune version n'est publiée")) \
        is False
    assert vmaj.doit_proposer(maj.Resultat(arme=True, detail="TimeoutError")) is False


def test_une_verification_desarmee_n_ouvre_rien():
    assert vmaj.doit_proposer(maj.Resultat(arme=False, detail="désarmée")) is False


# --------------------------------------------------------------------------- #
#  Ce qui est installable, et ce qui ne l'est pas
# --------------------------------------------------------------------------- #

def test_gele_avec_ses_deux_fichiers_c_est_installable():
    assert vmaj.installable(_resultat(), gele=True) is True
    assert vmaj.motif_de_refus(_resultat(), gele=True) == ""


def test_depuis_les_sources_rien_ne_s_installe():
    """On ne remplace pas l'arbre de travail de quelqu'un qui a cloné le dépôt par une
    installation. `core.maj.installer` refuse au même endroit, et pour la même raison."""
    assert vmaj.installable(_resultat(), gele=False) is False
    assert "git pull" in vmaj.motif_de_refus(_resultat(), gele=False)


def test_sans_fichier_d_empreintes_on_ne_telecharge_meme_pas():
    """⚠ La condition la moins évidente des trois, et la plus importante : un installeur qu'on
    ne peut pas vérifier vaut MOINS qu'un lien vers la page, parce qu'il aurait l'air
    vérifié."""
    sans = _resultat(assets=(INSTALLEUR,))
    assert vmaj.installable(sans, gele=True) is False
    assert "empreintes" in vmaj.motif_de_refus(sans, gele=True)


def test_sans_installeur_non_plus():
    """⚠ C'est le cas de **toutes** les releases publiées avant ce lot."""
    assert vmaj.installable(_resultat(assets=()), gele=True) is False


# --------------------------------------------------------------------------- #
#  Ce que la fenêtre dit avant le clic
# --------------------------------------------------------------------------- #

def test_la_proposition_dit_le_poids_avant_les_115_secondes():
    texte = vmaj.phrase_proposition(_resultat(), "2.33.0", gele=True)
    assert "292,1 Mio" in texte
    assert "2.33.0" in texte and "99.0.0" in texte


def test_la_proposition_dit_ce_que_l_empreinte_NE_protege_PAS():
    """⚠ Condition écrite du lot : « cela doit être écrit à l'écran, pas seulement ici ». Qui
    lit « empreinte vérifiée » comprend « signé » s'il n'a pas lu le reste, et ce serait
    faux."""
    texte = vmaj.phrase_proposition(_resultat(), "2.33.0", gele=True)
    assert "NE remplace PAS une signature de code" in texte
    assert "aucun certificat" in texte


def test_la_proposition_rassure_sur_ce_qui_n_est_pas_touche():
    texte = vmaj.phrase_proposition(_resultat(), "2.33.0", gele=True)
    assert "projets" in texte and "poids de modèles" in texte


def test_hors_gel_la_proposition_donne_la_page_et_pas_un_poids():
    texte = vmaj.phrase_proposition(_resultat(), "2.33.0", gele=False)
    assert "git pull" in texte
    assert "releases" in texte
    assert "292,1 Mio" not in texte


# --------------------------------------------------------------------------- #
#  Les deux phrases de bord
# --------------------------------------------------------------------------- #

def test_l_echec_d_empreinte_dit_ce_qui_a_ete_fait_du_fichier():
    """⚠ « Empreinte invalide » tout seul laisse quelqu'un chercher sur son disque un
    installeur qu'on a déjà effacé — ou pire, le lancer."""
    texte = vmaj.phrase_echec_empreinte("aaa", "bbb")
    assert "aaa" in texte and "bbb" in texte
    assert "effacé" in texte and "rien n'a été installé" in texte


def test_une_empreinte_absente_le_dit_plutot_que_d_afficher_du_vide():
    assert "absente" in vmaj.phrase_echec_empreinte("", "bbb")


@pytest.mark.parametrize("lus,total,attendu", [
    (0, 0, "0,0 Mio reçus"),
    (1024 * 1024, 0, "1,0 Mio reçus"),
    (1024 * 1024, 4 * 1024 * 1024, "1,0 Mio sur 4,0 Mio (25 %)"),
])
def test_la_progression_n_invente_pas_de_pourcentage(lus, total, attendu):
    assert vmaj.phrase_progres(lus, total) == attendu


def test_silencieuse_par_defaut_est_faux():
    assert vmaj.silencieuse(None) is False
    assert vmaj.silencieuse({}) is False
