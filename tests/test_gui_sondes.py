# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Alexandre Tournel

"""Les trois sondes de l'accueil (`gui/sondes.py`) — **sans PySide6, sans réseau, sans modèle**.

## Ce que ce fichier protège

Le critère 7 du `PLAN-31` : « Aucune sonde réseau sur le fil d'affichage ; l'accueil s'affiche
avec un endpoint LLM injoignable, et le dit, en moins d'une seconde. »

La moitié « fil d'affichage » se vérifie dans `tests/test_gui_fenetre.py`, qui construit la
fenêtre. La moitié **décision** se vérifie ici : trois états et pas deux, un verdict qui ne
lève jamais, un délai court, et un code d'erreur HTTP qui reste une RÉPONSE.

⚠ Aucun appel réseau réel n'est fait par ces tests. `httpx.get` est remplacé ; c'est le seul
moyen de vérifier le comportement sur un serveur injoignable sans dépendre de ce qui tourne sur
la machine qui lance la suite — laquelle a précisément un Ollama vivant.
"""
from __future__ import annotations

import pytest

from gui import sondes as snd


# --------------------------------------------------------------------------- #
# Trois états, pas deux
# --------------------------------------------------------------------------- #

def test_l_accueil_part_avec_trois_marqueurs_inconnus():
    """⚠ `INCONNU` n'est pas une commodité d'implémentation : c'est l'état RÉEL pendant la
    seconde qui suit le lancement. Le confondre avec « injoignable » ferait dire à l'accueil
    quelque chose de faux à chaque démarrage."""
    inconnues = snd.inconnues()
    assert len(inconnues) == 3
    assert {s.etat for s in inconnues} == {snd.INCONNU}
    assert [s.nom for s in inconnues] == ["Serveur LLM", "Poids de détection", "Pandoc"]
    for sonde in inconnues:
        assert "en cours" in sonde.ligne()


def test_chaque_etat_a_son_symbole_et_ils_sont_distincts():
    """L'état ne doit pas se lire à la seule couleur — `PLAN-19`, accessibilité."""
    assert set(snd.SYMBOLES) == {snd.JOIGNABLE, snd.INJOIGNABLE, snd.INCONNU}
    assert len(set(snd.SYMBOLES.values())) == 3


def test_la_ligne_porte_le_verdict_et_ce_qu_on_a_regarde():
    sonde = snd.Sonde("Pandoc", snd.JOIGNABLE, "C:/pandoc.exe")
    assert "Pandoc" in sonde.ligne()
    assert "disponible" in sonde.ligne()
    assert "C:/pandoc.exe" in sonde.ligne()


# --------------------------------------------------------------------------- #
# La sonde LLM — un GET, rien d'autre
# --------------------------------------------------------------------------- #

class _Reponse:
    def __init__(self, code: int):
        self.status_code = code


def test_un_endpoint_injoignable_est_dit_et_ne_leve_pas(monkeypatch):
    """Le critère 7 : « l'accueil s'affiche avec un endpoint LLM injoignable, **et le dit** »."""
    import httpx

    def _echoue(*_a, **_k):
        raise httpx.ConnectError("connexion refusée")

    monkeypatch.setattr(httpx, "get", _echoue)
    sonde = snd.sonder_llm({"llm": {"base_url": "http://localhost:11434/v1"}})
    assert sonde.etat == snd.INJOIGNABLE
    assert "localhost:11434" in sonde.detail
    assert "ConnectError" in sonde.detail
    assert sonde.remede, "un verdict négatif dit quoi faire"


def test_un_delai_depasse_est_un_injoignable_comme_un_autre(monkeypatch):
    """⚠ C'est LE cas qui interdit de sonder sur le fil d'affichage : un Ollama arrêté ne
    répond pas par un refus immédiat, il répond par un délai d'attente."""
    import httpx

    def _expire(*_a, **_k):
        raise httpx.ConnectTimeout("délai dépassé")

    monkeypatch.setattr(httpx, "get", _expire)
    assert snd.sonder_llm({}).etat == snd.INJOIGNABLE


def test_un_code_d_erreur_HTTP_reste_une_reponse(monkeypatch):
    """⚠ Un serveur qui rend 404 sur sa racine EST joignable — c'est ce que fait LM Studio.
    Ne retenir que 200 dirait « injoignable » d'un serveur qui tourne."""
    import httpx

    monkeypatch.setattr(httpx, "get", lambda *a, **k: _Reponse(404))
    sonde = snd.sonder_llm({})
    assert sonde.etat == snd.JOIGNABLE
    assert "404" in sonde.detail


def test_le_v1_est_retire_avant_le_GET(monkeypatch):
    """`/v1` est le préfixe de l'API compatible OpenAI, pas une page. On sonde la racine."""
    import httpx

    vues = []
    monkeypatch.setattr(httpx, "get",
                        lambda url, **k: vues.append(url) or _Reponse(200))
    snd.sonder_llm({"llm": {"base_url": "http://ailleurs:1234/v1"}})
    assert vues == ["http://ailleurs:1234/"]


def test_le_delai_est_court_et_c_est_delibere(monkeypatch):
    """⚠ À comparer aux 30 s de `core.llm.test_connection`, qui fait une vraie génération.
    Deux questions différentes, deux budgets différents — et confondre les deux ferait de
    l'accueil une page qui bloque."""
    import httpx

    vus = []
    monkeypatch.setattr(httpx, "get",
                        lambda url, timeout=None: vus.append(timeout) or _Reponse(200))
    snd.sonder_llm({})
    assert vus == [snd.DELAI_RESEAU]
    assert snd.DELAI_RESEAU <= 3.0


def test_l_endpoint_par_defaut_est_celui_du_depot():
    assert snd.url_llm({}) == "http://localhost:11434/v1"
    assert snd.url_llm({"llm": {"base_url": "http://x:1/v1"}}) == "http://x:1/v1"


# --------------------------------------------------------------------------- #
# Les poids — un `is_file()`, aucun chargement
# --------------------------------------------------------------------------- #

def test_la_sonde_des_poids_lit_la_cle_que_la_brique_lit(tmp_path):
    """⚠ `manga.detection.model_path` — la clé exacte que `BubbleDetector.depuis_config` lit.
    En inventer une seconde ferait dire à l'accueil que les poids sont absents alors qu'ils
    sont là, ou l'inverse ; les deux mensonges se valent."""
    poids = tmp_path / "detecteur.onnx"
    poids.write_bytes(b"x" * 2048)
    config = {"manga": {"detection": {"model_path": str(poids)}}}
    assert snd.chemins_poids(config) == [poids]
    sonde = snd.sonder_poids(config)
    assert sonde.etat == snd.JOIGNABLE
    assert "detecteur.onnx" in sonde.detail


def test_des_poids_absents_sont_dits_avec_leur_chemin_et_leur_remede(tmp_path):
    config = {"manga": {"detection": {"model_path": str(tmp_path / "absent.onnx")}}}
    sonde = snd.sonder_poids(config)
    assert sonde.etat == snd.INJOIGNABLE
    assert "absent.onnx" in sonde.detail
    assert "manga_models/README.md" in sonde.remede
    assert "GPL-3.0" in sonde.remede, "la licence du détecteur est nommée, comme partout"


def test_sans_cle_on_retombe_sur_le_chemin_du_depot():
    assert snd.chemins_poids({}) == [snd.POIDS_PAR_DEFAUT]


# --------------------------------------------------------------------------- #
# Pandoc
# --------------------------------------------------------------------------- #

def test_pandoc_absent_est_dit_avec_son_remede(monkeypatch):
    monkeypatch.setattr(snd.shutil, "which", lambda _n: None)
    sonde = snd.sonder_pandoc()
    assert sonde.etat == snd.INJOIGNABLE
    assert "pandoc.org" in sonde.remede


def test_pandoc_present_porte_son_chemin(monkeypatch):
    monkeypatch.setattr(snd.shutil, "which", lambda _n: "C:/Pandoc/pandoc.exe")
    sonde = snd.sonder_pandoc()
    assert sonde.etat == snd.JOIGNABLE
    assert "pandoc.exe" in sonde.detail


# --------------------------------------------------------------------------- #
# L'ensemble
# --------------------------------------------------------------------------- #

def test_sonder_tout_rend_trois_verdicts_dans_l_ordre_d_affichage(monkeypatch, tmp_path):
    import httpx

    monkeypatch.setattr(httpx, "get", lambda *a, **k: _Reponse(200))
    monkeypatch.setattr(snd.shutil, "which", lambda _n: None)
    sondes = snd.sonder_tout({"manga": {"detection": {"model_path": str(tmp_path / "n.onnx")}}})
    assert [s.nom for s in sondes] == ["Serveur LLM", "Poids de détection", "Pandoc"]
    assert [s.etat for s in sondes] == [snd.JOIGNABLE, snd.INJOIGNABLE, snd.INJOIGNABLE]


def test_aucune_sonde_ne_leve_quoi_qu_il_arrive(monkeypatch):
    """⚠ Une sonde qui lèverait ferait tomber la tâche, donc laisserait les trois marqueurs en
    « inconnu » pour toute la session — un défaut muet, le pire genre."""
    import httpx

    def _explose(*_a, **_k):
        raise RuntimeError("quelque chose d'inattendu")

    monkeypatch.setattr(httpx, "get", _explose)
    sondes = snd.sonder_tout({})
    assert len(sondes) == 3
    for sonde in sondes:
        assert sonde.etat in (snd.JOIGNABLE, snd.INJOIGNABLE, snd.INCONNU)


def test_le_module_n_importe_pas_qt():
    """Règle de couche du dépôt : tout ce qui décide se teste sans PySide6."""
    import ast
    from pathlib import Path

    source = (Path(__file__).resolve().parent.parent / "gui" / "sondes.py")
    arbre = ast.parse(source.read_text(encoding="utf-8"))
    noms = []
    for noeud in ast.walk(arbre):
        if isinstance(noeud, ast.Import):
            noms += [a.name for a in noeud.names]
        elif isinstance(noeud, ast.ImportFrom) and noeud.module:
            noms.append(noeud.module)
    assert not [n for n in noms if "PySide6" in n], noms


@pytest.mark.parametrize("etat", [snd.JOIGNABLE, snd.INJOIGNABLE, snd.INCONNU])
def test_les_trois_etats_ont_un_verdict_lisible(etat):
    ligne = snd.Sonde("X", etat).ligne()
    assert ligne.startswith(snd.SYMBOLES[etat])
    assert "X" in ligne


# --------------------------------------------------------------------------- #
#  Lot 36 — le pont vers le vocabulaire du diagnostic
# --------------------------------------------------------------------------- #

def test_une_sonde_joignable_devient_un_verdict_conforme():
    from core import diagnostic as diag

    verdict = snd.verdict(snd.Sonde("Pandoc", snd.JOIGNABLE, "C:/bin/pandoc"))
    assert verdict.gravite == diag.CONFORME
    assert verdict.identifiant == "pandoc"
    assert verdict.brique == diag.LN


def test_une_sonde_inconnue_est_une_INFORMATION_et_jamais_un_bloquant():
    """⚠ « Je n'ai pas encore regardé » n'est pas « c'est cassé ». C'est la règle des trois
    états de ce module, portée dans l'autre vocabulaire."""
    from core import diagnostic as diag

    verdict = snd.verdict(snd.Sonde("Serveur LLM", snd.INCONNU))
    assert verdict.gravite == diag.INFORMATION
    assert verdict.geste


def test_une_sonde_injoignable_est_DEGRADE_et_pas_BLOQUANT():
    """⚠ Cette sonde n'a fait qu'un GET sur une racine. Conclure au blocage sur une mesure
    aussi superficielle afficherait un verdict plus dur que ce qu'on a mesuré — le diagnostic
    complet, lui, a le droit, parce qu'il a vraiment essayé de générer."""
    from core import diagnostic as diag

    verdict = snd.verdict(snd.Sonde("Serveur LLM", snd.INJOIGNABLE, "url", remede="démarre-le"))
    assert verdict.gravite == diag.DEGRADE
    assert verdict.brique == diag.SOCLE
    assert diag.bloquants_pour((diag.Section("", (verdict,)),), diag.MANGA) == ()


def test_les_identifiants_des_sondes_sont_CEUX_des_doctors():
    """⚠ C'est ce qui empêche l'accueil et la page Diagnostic de se contredire : ils parlent du
    même point, avec le même nom, et le remède n'est plus écrit deux fois."""
    identifiants = {snd.verdict(s).identifiant for s in snd.inconnues()}
    assert identifiants == {"serveur_llm", "poids_detection", "pandoc"}


def test_une_sonde_injoignable_recupere_le_geste_du_catalogue_de_reparations():
    from core import reparations as rep

    verdict = snd.verdict(snd.Sonde("Poids de détection", snd.INJOIGNABLE, "absent"))
    assert verdict.geste
    assert verdict.reparation == "poids_detection"
    assert verdict.reparable is rep.par_identifiant("poids_detection").automatique


def test_verdicts_traite_les_trois_sondes_dans_l_ordre():
    verdicts = snd.verdicts(snd.inconnues())
    assert [v.identifiant for v in verdicts] == ["serveur_llm", "poids_detection", "pandoc"]
