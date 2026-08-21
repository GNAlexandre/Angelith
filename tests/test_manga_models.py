# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Alexandre Tournel

"""Récupération automatique des poids de modèles (`manga/models.py`).

⚠ Aucun test ici ne touche le réseau : `urllib.request.urlopen` est systématiquement remplacé.
Un seul appel réel coûterait 104 Mo par exécution de la suite.
"""
from __future__ import annotations

import io
import urllib.error
from pathlib import Path

import pytest

from manga import models


class _Reponse(io.BytesIO):
    """Minimum vital d'un objet renvoyé par `urlopen` : un flux et des en-têtes."""

    def __init__(self, charge: bytes, longueur: int | None = None):
        super().__init__(charge)
        self.headers = {"Content-Length": str(longueur if longueur is not None else len(charge))}

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()
        return False


def _faux_reseau(monkeypatch, charge: bytes, longueur: int | None = None):
    vus: list[str] = []

    def _urlopen(requete, *a, **k):
        vus.append(getattr(requete, "full_url", requete))
        return _Reponse(charge, longueur)

    monkeypatch.setattr(models.urllib.request, "urlopen", _urlopen)
    return vus


# --------------------------------------------------------------------------- #
# Le fichier présent n'est jamais retéléchargé
# --------------------------------------------------------------------------- #

def test_un_modele_deja_la_nest_pas_retelecharge(tmp_path, monkeypatch):
    cible = tmp_path / "detecteur.onnx"
    cible.write_bytes(b"deja la")
    vus = _faux_reseau(monkeypatch, b"autre chose")

    assert models.assurer_detecteur(cible) == cible
    assert vus == [], "aucun appel réseau ne devait partir"
    assert cible.read_bytes() == b"deja la"


def test_un_fichier_vide_est_considere_absent(tmp_path, monkeypatch):
    """Un `.onnx` de 0 octet est le résidu typique d'un disque plein : le traiter comme
    présent condamnerait l'utilisateur à un message d'ONNX Runtime incompréhensible."""
    cible = tmp_path / "detecteur.onnx"
    cible.touch()
    _faux_reseau(monkeypatch, b"x" * 500)

    models.assurer_detecteur(cible, sha256=None, octets_attendus=None)
    assert cible.read_bytes() == b"x" * 500


# --------------------------------------------------------------------------- #
# Téléchargement
# --------------------------------------------------------------------------- #

def test_le_modele_manquant_est_telecharge(tmp_path, monkeypatch):
    cible = tmp_path / "sous" / "dossier" / "detecteur.onnx"
    vus = _faux_reseau(monkeypatch, b"poids" * 100)

    models.assurer_detecteur(cible, sha256=None, octets_attendus=None)
    assert cible.exists() and cible.read_bytes() == b"poids" * 100
    assert vus == [models.DETECTEUR_URL]


def test_l_url_de_config_est_respectee(tmp_path, monkeypatch):
    vus = _faux_reseau(monkeypatch, b"poids")
    models.assurer_detecteur(tmp_path / "m.onnx", url="https://exemple.test/m.onnx",
                             sha256=None, octets_attendus=None)
    assert vus == ["https://exemple.test/m.onnx"]


def test_l_avancement_est_annonce(tmp_path, monkeypatch):
    """104 Mo en silence ressemblent à un pipeline planté."""
    _faux_reseau(monkeypatch, b"x" * (3 << 20))
    lignes: list[str] = []
    models.assurer_detecteur(tmp_path / "m.onnx", sha256=None, octets_attendus=None,
                             dire=lignes.append)
    assert any("Téléchargement" in ligne for ligne in lignes)
    assert any("prêt" in ligne for ligne in lignes)


# --------------------------------------------------------------------------- #
# Rien de tronqué ne doit jamais prendre la place du modèle
# --------------------------------------------------------------------------- #

def test_un_telechargement_court_est_refuse_et_ne_laisse_rien(tmp_path, monkeypatch):
    """Un serveur qui répond une page d'erreur en 200 produit un fichier court. Le dire ici
    vaut mieux que de laisser ONNX Runtime refuser un `.onnx` invalide à chaque relance."""
    cible = tmp_path / "m.onnx"
    _faux_reseau(monkeypatch, b"<html>404</html>")

    with pytest.raises(SystemExit, match="incomplet"):
        models.assurer_detecteur(cible, sha256=None, octets_attendus=10_000_000)
    assert not cible.exists()
    assert not list(tmp_path.glob("*.part")), "le fichier partiel doit être nettoyé"


def test_une_erreur_reseau_ne_laisse_pas_de_fichier(tmp_path, monkeypatch):
    def _boum(*a, **k):
        raise urllib.error.URLError("réseau injoignable")

    monkeypatch.setattr(models.urllib.request, "urlopen", _boum)
    cible = tmp_path / "m.onnx"
    with pytest.raises(SystemExit, match="impossible"):
        models.assurer_detecteur(cible)
    assert not cible.exists()
    assert not list(tmp_path.glob("*.part"))


def test_le_fichier_nest_renomme_qu_a_la_fin(tmp_path, monkeypatch):
    """L'invariant qui protège le cache : pendant l'écriture, la destination n'existe pas."""
    cible = tmp_path / "m.onnx"
    etats: list[bool] = []

    class _Espion(_Reponse):
        def read(self, n=-1):
            etats.append(cible.exists())
            return super().read(n)

    monkeypatch.setattr(models.urllib.request, "urlopen",
                        lambda *a, **k: _Espion(b"y" * (2 << 20)))
    models.assurer_detecteur(cible, sha256=None, octets_attendus=None)
    assert etats and not any(etats), "la destination existait avant la fin du téléchargement"
    assert cible.exists()


# --------------------------------------------------------------------------- #
# Empreinte et repli manuel
# --------------------------------------------------------------------------- #

def test_une_empreinte_inattendue_avertit_sans_bloquer(tmp_path, monkeypatch):
    """Un dépôt amont qui republie ses poids ne doit pas arrêter le pipeline — seulement
    signaler que ce n'est plus le fichier de référence."""
    _faux_reseau(monkeypatch, b"des poids differents")
    lignes: list[str] = []
    cible = tmp_path / "m.onnx"
    models.assurer_detecteur(cible, sha256="0" * 64, octets_attendus=None, dire=lignes.append)

    assert cible.exists(), "le modèle doit être conservé malgré l'écart d'empreinte"
    assert any("Empreinte inattendue" in ligne for ligne in lignes)


def test_une_empreinte_conforme_ne_dit_rien(tmp_path, monkeypatch):
    charge = b"des poids"
    _faux_reseau(monkeypatch, charge)
    import hashlib
    lignes: list[str] = []
    models.assurer_detecteur(tmp_path / "m.onnx", sha256=hashlib.sha256(charge).hexdigest(),
                             octets_attendus=None, dire=lignes.append)
    assert not any("Empreinte" in ligne for ligne in lignes)


def test_auto_false_garde_le_message_actionnable(tmp_path, monkeypatch):
    vus = _faux_reseau(monkeypatch, b"poids")
    with pytest.raises(SystemExit, match="introuvable"):
        models.assurer_detecteur(tmp_path / "absent.onnx", auto=False)
    assert vus == [], "auto=False ne doit RIEN télécharger"


def test_empreinte_lit_le_fichier_par_morceaux(tmp_path):
    import hashlib
    contenu = b"z" * (5 << 20)
    fichier = tmp_path / "gros.bin"
    fichier.write_bytes(contenu)
    assert models.empreinte(fichier) == hashlib.sha256(contenu).hexdigest()


def test_la_constante_pointe_vers_le_modele_documente():
    """`manga_models/README.md` et le code doivent nommer la même URL : c'est le repli manuel
    quand le téléchargement automatique est coupé."""
    readme = Path("manga_models/README.md").read_text(encoding="utf-8")
    assert models.DETECTEUR_URL in readme.replace("`", "").replace("\n", "")
