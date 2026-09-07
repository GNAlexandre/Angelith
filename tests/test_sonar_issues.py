# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Alexandre Tournel

"""Extraction des issues Sonar (`tools/sonar_issues.py`), à 0 % de couverture jusqu'ici.

## Pourquoi ce fichier existe

L'outil est le seul chemin vers les issues du projet — SonarQube Cloud n'offre aucun export
depuis son interface. Il n'était couvert par rien, alors qu'il porte deux invariants dont
son propre module dit qu'ils comptent :

- **la pagination ne doit jamais s'arrêter en silence.** Une extraction tronquée qui
  ressemble à une extraction complète, c'est le défaut que le dépôt combat partout ailleurs
  (« la CI verte qui ne teste plus rien ») ;
- **les security hotspots vivent dans un endpoint séparé.** Les oublier donnerait une
  extraction « complète » sans la sécurité.

⚠ Aucun test ici ne touche le réseau : `_appel` est remplacé par une table de réponses.
Aucun ne lit non plus le vrai jeton — `.sonar-token` est un secret, et le premier test
vérifie justement que l'environnement a la priorité sur lui.
"""
from __future__ import annotations

import json
import sys

import pytest

from tools import sonar_issues as si


# --- résolution du jeton ---------------------------------------------------------

def test_la_variable_d_environnement_prime_sur_le_fichier(monkeypatch, tmp_path):
    monkeypatch.setenv("SONAR_TOKEN", "jeton-d-environnement")
    monkeypatch.setattr(si, "FICHIER_JETON", tmp_path / ".sonar-token")
    (tmp_path / ".sonar-token").write_text("jeton-de-fichier", encoding="utf-8")
    assert si._jeton() == "jeton-d-environnement"


def test_le_fichier_sert_de_repli(monkeypatch, tmp_path):
    monkeypatch.delenv("SONAR_TOKEN", raising=False)
    fichier = tmp_path / ".sonar-token"
    fichier.write_text("  jeton-de-fichier\n", encoding="utf-8")
    monkeypatch.setattr(si, "FICHIER_JETON", fichier)
    assert si._jeton() == "jeton-de-fichier"


def test_un_jeton_vide_ne_compte_pas_pour_un_jeton(monkeypatch, tmp_path):
    """Un `SONAR_TOKEN=` ou un fichier vide doit échouer comme une absence, pas partir en
    requête avec un en-tête `Bearer ` creux dont l'erreur serait un 401 opaque."""
    monkeypatch.setenv("SONAR_TOKEN", "   ")
    fichier = tmp_path / ".sonar-token"
    fichier.write_text("\n", encoding="utf-8")
    monkeypatch.setattr(si, "FICHIER_JETON", fichier)
    with pytest.raises(SystemExit, match="JETON UTILISATEUR"):
        si._jeton()


def test_l_absence_totale_nomme_la_variable_et_le_fichier(monkeypatch, tmp_path):
    monkeypatch.delenv("SONAR_TOKEN", raising=False)
    # Le fichier est nommé comme en production : le message cite `FICHIER_JETON.name`, et
    # c'est ce nom-là que l'utilisateur doit lire pour savoir quoi créer.
    monkeypatch.setattr(si, "FICHIER_JETON", tmp_path / ".sonar-token")
    with pytest.raises(SystemExit) as exc:
        si._jeton()
    assert "SONAR_TOKEN" in str(exc.value) and ".sonar-token" in str(exc.value)


# --- nom de fichier --------------------------------------------------------------

@pytest.mark.parametrize("composant, attendu", [
    ("GNAlexandre_Yume-Trad:core/cli.py", "core/cli.py"),
    ("core/cli.py", "core/cli.py"),
    ("GNAlexandre_Yume-Trad:tools/a:b.py", "tools/a:b.py"),
    ("", ""),
])
def test_le_composant_est_reduit_au_chemin(composant, attendu):
    assert si._fichier(composant) == attendu


# --- pagination ------------------------------------------------------------------

def _fausse_api(monkeypatch, pages: list[dict]):
    """Remplace `_appel` par une lecture de `pages`, indexée par le numéro de page."""
    vus = []

    def _appel(chemin, params, jeton):
        vus.append((chemin, params["p"], params["ps"]))
        return pages[params["p"] - 1]

    monkeypatch.setattr(si, "_appel", _appel)
    return vus


def test_toutes_les_pages_sont_lues(monkeypatch):
    vus = _fausse_api(monkeypatch, [
        {"issues": [{"n": i} for i in range(500)], "total": 700},
        {"issues": [{"n": i} for i in range(200)], "total": 700},
    ])
    tout = si._pagine("/api/issues/search", {}, "issues", "jeton")
    assert len(tout) == 700
    assert [p for _, p, _ in vus] == [1, 2]


def test_une_seule_page_ne_declenche_pas_de_seconde_requete(monkeypatch):
    vus = _fausse_api(monkeypatch, [{"issues": [{"n": 1}], "total": 1}])
    assert len(si._pagine("/api/issues/search", {}, "issues", "jeton")) == 1
    assert len(vus) == 1


def test_un_total_annonce_sous_paging_est_lu_aussi(monkeypatch):
    """L'API rend `total` tantôt à la racine, tantôt sous `paging`. Lire une seule des deux
    formes ferait croire l'extraction finie après une page."""
    _fausse_api(monkeypatch, [
        {"hotspots": [{"n": i} for i in range(500)], "paging": {"total": 501}},
        {"hotspots": [{"n": 500}], "paging": {"total": 501}},
    ])
    assert len(si._pagine("/api/hotspots/search", {}, "hotspots", "jeton")) == 501


def test_une_page_vide_avant_la_fin_est_signalee_et_non_tue(monkeypatch, capsys):
    """LE point du module : « un `break` silencieux ici rendrait une extraction tronquée qui
    ressemble à une extraction complète »."""
    _fausse_api(monkeypatch, [
        {"issues": [{"n": i} for i in range(500)], "total": 900},
        {"issues": [], "total": 900},
    ])
    tout = si._pagine("/api/issues/search", {}, "issues", "jeton")
    assert len(tout) == 500
    assert "500/900" in capsys.readouterr().err


def test_le_plafond_de_l_api_est_une_erreur_pas_une_troncature(monkeypatch):
    """`p * ps` est plafonné côté serveur. Au-delà, s'arrêter rendrait une extraction
    silencieusement incomplète — l'outil doit exiger un filtre."""
    pages = [{"issues": [{"n": i} for i in range(500)], "total": 99_999}
             for _ in range(40)]
    _fausse_api(monkeypatch, pages)
    with pytest.raises(SystemExit, match="Plafond"):
        si._pagine("/api/issues/search", {}, "issues", "jeton")


# --- le rapport produit ----------------------------------------------------------

ISSUE = {
    "component": "GNAlexandre_Yume-Trad:core/cli.py", "line": 52, "rule": "python:S3776",
    "severity": "CRITICAL", "effort": "20min", "message": "Refactor this function",
    "impacts": [{"softwareQuality": "MAINTAINABILITY", "severity": "HIGH"}],
}
HOTSPOT = {
    "component": "GNAlexandre_Yume-Trad:core/power.py", "line": 201,
    "ruleKey": "python:S4823", "vulnerabilityProbability": "LOW",
    "securityCategory": "others", "message": "Make sure that using this is safe",
}


def _lancer(monkeypatch, tmp_path, issues, hotspots, argv=()):
    monkeypatch.setattr(si, "_jeton", lambda: "jeton")
    monkeypatch.setattr(si, "_pagine",
                        lambda chemin, params, cle, jeton:
                        issues if cle == "issues" else hotspots)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(sys, "argv", ["sonar_issues.py", *argv])
    assert si.main() == 0
    return ((tmp_path / "sonar-issues.md").read_text(encoding="utf-8"),
            json.loads((tmp_path / "sonar-issues.json").read_text(encoding="utf-8")))


def test_le_rapport_porte_les_deux_comptes_et_le_json_brut(monkeypatch, tmp_path):
    md, brut = _lancer(monkeypatch, tmp_path, [ISSUE], [HOTSPOT])
    assert "1 issue(s) ouverte(s), 1 hotspot(s) à relire." in md
    assert brut == {"issues": [ISSUE], "hotspots": [HOTSPOT]}


def test_les_issues_sont_groupees_par_fichier_et_comptees_par_regle(monkeypatch, tmp_path):
    autre = {**ISSUE, "component": "GNAlexandre_Yume-Trad:manga/psd.py", "line": 8,
             "rule": "python:S1192"}
    md, _ = _lancer(monkeypatch, tmp_path, [ISSUE, autre], [])
    assert "### `core/cli.py`" in md and "### `manga/psd.py`" in md
    assert "| `python:S3776` | 1 |" in md and "| `python:S1192` | 1 |" in md
    # Ordre alphabétique des fichiers : un rapport qu'on relit d'une version à l'autre.
    assert md.index("### `core/cli.py`") < md.index("### `manga/psd.py`")


def test_les_hotspots_ont_leur_section_a_part(monkeypatch, tmp_path):
    """Ils viennent d'un autre endpoint et ne se corrigent pas d'office : les fondre dans la
    liste des issues inviterait à les traiter comme telles."""
    md, _ = _lancer(monkeypatch, tmp_path, [ISSUE], [HOTSPOT])
    assert "## Security hotspots (à relire, pas à corriger d'office)" in md
    assert "`core/power.py:201`" in md


def test_sans_hotspot_la_section_disparait(monkeypatch, tmp_path):
    md, _ = _lancer(monkeypatch, tmp_path, [ISSUE], [])
    assert "Security hotspots" not in md


def test_l_impact_prime_sur_la_severite_historique(monkeypatch, tmp_path):
    """Sonar publie les deux ; `impacts` est le modèle actuel. Afficher `CRITICAL` quand la
    qualité logicielle dit `MAINTAINABILITY:HIGH` mélangerait deux échelles."""
    md, _ = _lancer(monkeypatch, tmp_path, [ISSUE], [])
    assert "MAINTAINABILITY:HIGH" in md
    sans_impact = {**ISSUE, "impacts": []}
    md2, _ = _lancer(monkeypatch, tmp_path, [sans_impact], [])
    assert "CRITICAL" in md2


def test_le_prefixe_de_sortie_est_configurable(monkeypatch, tmp_path):
    monkeypatch.setattr(si, "_jeton", lambda: "jeton")
    monkeypatch.setattr(si, "_pagine", lambda *a, **k: [])
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(sys, "argv", ["sonar_issues.py", "--sortie", "releve"])
    assert si.main() == 0
    assert (tmp_path / "releve.md").is_file() and (tmp_path / "releve.json").is_file()


def test_une_extraction_vide_reste_un_rapport_valide(monkeypatch, tmp_path):
    """Zéro issue est un RÉSULTAT, pas une panne : le fichier doit exister et le dire."""
    md, brut = _lancer(monkeypatch, tmp_path, [], [])
    assert "0 issue(s) ouverte(s), 0 hotspot(s) à relire." in md
    assert brut == {"issues": [], "hotspots": []}


# --- l'appel HTTP lui-même -------------------------------------------------------

class _Reponse:
    def __init__(self, charge: bytes):
        self._charge = charge

    def read(self):
        return self._charge

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False


def test_l_appel_porte_le_jeton_en_bearer_et_encode_ses_parametres(monkeypatch):
    vus = {}

    def _urlopen(req, timeout=None):
        vus["url"] = req.full_url
        vus["auth"] = req.get_header("Authorization")
        return _Reponse(b'{"issues": []}')

    monkeypatch.setattr("urllib.request.urlopen", _urlopen)
    assert si._appel("/api/issues/search", {"branch": "main", "p": 1}, "jeton") == {"issues": []}
    assert vus["auth"] == "Bearer jeton"
    assert vus["url"].startswith(f"{si.BASE}/api/issues/search?")
    assert "branch=main" in vus["url"] and "p=1" in vus["url"]


def test_une_erreur_http_nomme_l_endpoint_et_le_detail_du_serveur(monkeypatch):
    """Un 401 nu ne dit pas si le jeton est faux ou si c'est le jeton d'analyse de la CI —
    c'est le corps de la réponse qui le dit, et il doit remonter."""
    import urllib.error

    def _urlopen(req, timeout=None):
        raise urllib.error.HTTPError(req.full_url, 401, "Unauthorized", {},
                                     __import__("io").BytesIO(b"Insufficient privileges"))

    monkeypatch.setattr("urllib.request.urlopen", _urlopen)
    with pytest.raises(SystemExit) as exc:
        si._appel("/api/issues/search", {}, "mauvais-jeton")
    assert "401" in str(exc.value)
    assert "/api/issues/search" in str(exc.value)
    assert "Insufficient privileges" in str(exc.value)
