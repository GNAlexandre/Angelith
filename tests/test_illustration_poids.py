# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Alexandre Tournel

"""`illustration/poids.py` — **12 Go ne se téléchargent pas comme 104 Mo**.

Trois propriétés distinguent ce module de `manga/models.py`, et chacune est ici parce que le
facteur cent la rend nécessaire :

1. `auto=False` par défaut — un téléchargement de plusieurs gigaoctets se demande ;
2. **reprise sur coupure** par requête `Range`, avec le cas du serveur qui l'ignore ;
3. l'empreinte est une **erreur**, pas un avertissement : un ONNX corrompu se voit à la
   première inférence, un GGUF de 12 Go mal repris produit du bruit plausible.

Aucun octet ne part sur le réseau : `urllib.request.urlopen` est remplacé par une fausse
réponse qui simule une coupure au milieu du fichier.
"""
import hashlib
import urllib.error

import pytest

from illustration import poids as poids_mod

CORPS = bytes(range(256)) * 64                            # 16 384 octets, sans hasard
SHA = hashlib.sha256(CORPS).hexdigest()


class _Reponse:
    """Une réponse HTTP de papier, avec son `status` et son `Content-Length`."""

    def __init__(self, octets: bytes, status: int, total_annonce: int) -> None:
        self._octets, self.status = octets, status
        self.headers = {"Content-Length": str(total_annonce)}
        self._lu = 0

    def read(self, taille=-1):
        if taille is None or taille < 0:
            morceau, self._lu = self._octets[self._lu:], len(self._octets)
            return morceau
        morceau = self._octets[self._lu:self._lu + taille]
        self._lu += len(morceau)
        return morceau

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False


class _Serveur:
    """Sert `CORPS`, honore ou ignore `Range`, et peut couper au milieu."""

    def __init__(self, *, honore_range=True, coupe_a=None) -> None:
        self.honore_range, self.coupe_a = honore_range, coupe_a
        self.demandes: list[int] = []

    def __call__(self, requete, timeout=None):
        entete = requete.headers.get("Range") or requete.headers.get("range") or ""
        depart = int(entete.split("=")[1].split("-")[0]) if entete else 0
        self.demandes.append(depart)
        if depart >= len(CORPS):
            # Ce que Hugging Face répond réellement quand on redemande au-delà de la fin.
            raise urllib.error.HTTPError(
                "http://exemple.invalide/m.gguf", 416, "Range Not Satisfiable", {}, None)
        if not self.honore_range:
            depart_effectif, status = 0, 200
        else:
            depart_effectif = depart
            status = 206 if depart else 200
        restant = CORPS[depart_effectif:]
        if self.coupe_a is not None and len(restant) > self.coupe_a:
            # Le serveur annonce la bonne longueur puis coupe : c'est le cas réel.
            tronque = restant[:self.coupe_a]
            self.coupe_a = None
            return _Reponse(tronque, status, len(restant))
        return _Reponse(restant, status, len(restant))


@pytest.fixture
def serveur(monkeypatch):
    def _poser(**champs):
        faux = _Serveur(**champs)
        monkeypatch.setattr(poids_mod.urllib.request, "urlopen", faux)
        return faux
    return _poser


def test_un_telechargement_complet_verifie_son_empreinte(tmp_path, serveur):
    serveur()
    cible = poids_mod.telecharger("http://exemple.invalide/m.gguf", tmp_path / "m.gguf",
                                  octets_attendus=len(CORPS), sha256=SHA, dire=lambda _: None)
    assert cible.read_bytes() == CORPS
    assert not (tmp_path / "m.gguf.part").exists(), "le .part doit être renommé, pas laissé"


def test_une_coupure_est_REPRISE_par_une_requete_Range(tmp_path, serveur):
    """Sur 12 Go, une coupure à 11 Go coûterait une soirée si on repartait de zéro."""
    faux = serveur(coupe_a=4096)
    poids_mod.telecharger("http://exemple.invalide/m.gguf", tmp_path / "m.gguf",
                          octets_attendus=len(CORPS), sha256=SHA, dire=lambda _: None)
    assert faux.demandes == [0, 4096], "la reprise doit repartir de la taille du .part"
    assert (tmp_path / "m.gguf").read_bytes() == CORPS


def test_un_serveur_qui_IGNORE_Range_repart_de_zero_sans_concatener(tmp_path, serveur):
    """Écrire à la suite produirait un fichier de taille double dont l'empreinte ne dirait
    rien de lisible. Le cas est détecté par le code de statut, pas supposé."""
    faux = serveur(honore_range=False, coupe_a=4096)
    messages: list[str] = []
    poids_mod.telecharger("http://exemple.invalide/m.gguf", tmp_path / "m.gguf",
                          octets_attendus=len(CORPS), sha256=SHA, dire=messages.append)
    assert faux.demandes == [0, 4096]
    assert (tmp_path / "m.gguf").read_bytes() == CORPS
    assert any("ignore les requêtes Range" in m for m in messages)


def test_une_taille_ATTENDUE_surestimee_est_corrigee_par_Content_Length(tmp_path, serveur):
    """Défaut réel, trouvé le 2026-08-29 en téléchargeant le VAE de Qwen-Image.

    `octets_attendus` était surestimé de 166 octets. Le code écrivait
    `total = total or (longueur + deja)` : l'estimation n'était donc JAMAIS corrigée par la
    taille annoncée par le serveur. Une fois le fichier entièrement reçu, il se croyait
    incomplet, relançait une requête Range au-delà de la fin, et le serveur répondait 416 —
    en boucle, jusqu'à l'abandon, sur un téléchargement pourtant réussi."""
    faux = serveur()
    surestime = len(CORPS) + 166
    cible = poids_mod.telecharger("http://exemple.invalide/m.gguf", tmp_path / "m.gguf",
                                  octets_attendus=surestime, sha256=SHA,
                                  dire=lambda _: None)
    assert cible.read_bytes() == CORPS
    assert faux.demandes == [0], "un seul aller réseau doit suffire"


def test_un_416_signifie_FICHIER_DEJA_COMPLET_et_non_une_panne(tmp_path, serveur):
    """416 « Range Not Satisfiable » est la réponse du serveur à « donne-moi ce qui suit la
    fin » : c'est un accusé de complétude, pas une coupure. Le traiter comme une panne
    consommait les trois tentatives puis levait, en conservant un fichier entier."""
    faux = serveur()
    partiel = tmp_path / "m.gguf.part"
    partiel.write_bytes(CORPS)                            # déjà complet sur le disque
    cible = poids_mod.telecharger("http://exemple.invalide/m.gguf", tmp_path / "m.gguf",
                                  octets_attendus=len(CORPS) + 999, sha256=SHA,
                                  dire=lambda _: None)
    assert cible.read_bytes() == CORPS
    assert faux.demandes == [len(CORPS)], "une seule requête, qui reçoit le 416"


def test_une_erreur_HTTP_qui_n_est_PAS_un_416_reste_une_panne(tmp_path, monkeypatch):
    """Le rattrapage du 416 ne doit pas avaler un 404 ou un 500."""
    def _casse(requete, timeout=None):
        raise urllib.error.HTTPError("http://exemple.invalide/m.gguf", 404,
                                     "Not Found", {}, None)

    monkeypatch.setattr(poids_mod.urllib.request, "urlopen", _casse)
    with pytest.raises(poids_mod.PoidsIntrouvable) as echec:
        poids_mod.telecharger("http://exemple.invalide/m.gguf", tmp_path / "m.gguf",
                              octets_attendus=len(CORPS), dire=lambda _: None, reprises=1)
    assert "404" in str(echec.value)


def test_une_empreinte_fausse_est_une_ERREUR_et_le_fichier_n_est_pas_installe(tmp_path,
                                                                              serveur):
    """`manga/models.py` se contente d'un avertissement ; ici c'est une erreur, et la
    différence n'est pas doctrinale : elle est de coût."""
    serveur()
    with pytest.raises(poids_mod.PoidsIntrouvable) as echec:
        poids_mod.telecharger("http://exemple.invalide/m.gguf", tmp_path / "m.gguf",
                              octets_attendus=len(CORPS), sha256="0" * 64,
                              dire=lambda _: None)
    assert "Empreinte inattendue" in str(echec.value)
    assert not (tmp_path / "m.gguf").exists()
    assert (tmp_path / "m.gguf.part").exists(), "le partiel est conservé pour diagnostic"


def test_un_echec_reseau_conserve_le_partiel_et_le_dit(tmp_path, monkeypatch):
    def _casse(requete, timeout=None):
        raise OSError("réseau coupé")

    monkeypatch.setattr(poids_mod.urllib.request, "urlopen", _casse)
    with pytest.raises(poids_mod.PoidsIntrouvable) as echec:
        poids_mod.telecharger("http://exemple.invalide/m.gguf", tmp_path / "m.gguf",
                              octets_attendus=len(CORPS), dire=lambda _: None, reprises=2)
    assert "reprendra où la coupure a eu lieu" in str(echec.value)


def test_assurer_poids_rend_un_fichier_deja_present(tmp_path):
    present = tmp_path / "m.gguf"
    present.write_bytes(b"x" * 16)
    assert poids_mod.assurer_poids(present, url="http://exemple.invalide/x") == present


def test_assurer_poids_ne_telecharge_rien_par_defaut(tmp_path, serveur):
    faux = serveur()
    with pytest.raises(poids_mod.PoidsIntrouvable):
        poids_mod.assurer_poids(tmp_path / "m.gguf", url="http://exemple.invalide/m.gguf")
    assert faux.demandes == [], "aucune requête ne doit partir sans `auto=True`"


def test_assurer_poids_telecharge_quand_on_le_demande(tmp_path, serveur):
    serveur()
    cible = poids_mod.assurer_poids(tmp_path / "m.gguf", url="http://exemple.invalide/m.gguf",
                                    auto=True, sha256=SHA, octets_attendus=len(CORPS),
                                    dire=lambda _: None)
    assert cible.read_bytes() == CORPS
