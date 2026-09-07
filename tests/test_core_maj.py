# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Alexandre Tournel

"""`core/maj.py` — **rien ne part sans opt-in explicite**, critère 12 du `PLAN-37`.

## Ce que ce fichier protège

Le projet promet « 100 % local, rien ne sort de la machine », et c'est l'un de ses six
différenciateurs annoncés. Un appel réseau au démarrage, même anodin, contredit la promesse.

Le garde-fou est donc double, et la seconde moitié est la seule qui vaille :

1. le `config.yaml` **publié** laisse `maj.verifier` à `false`. Vérifié sur
   `git show HEAD:config.yaml`, et pas sur le fichier de travail — c'est la leçon du lot 27,
   où six valeurs de travail d'une machine étaient entrées dans un commit qui parlait de
   polices de manga, armant une brique entière sans que personne le voie ;
2. **désarmé, le module ne peut pas appeler le réseau** — vérifié en lui donnant un `httpx`
   dont le `get` lève. Une affirmation « il n'appelle pas » se teste ; sinon c'est une
   intention.

⚠ Aucun test de ce fichier ne fait d'appel réseau réel. Le seul qui traverse `httpx` reçoit un
double, comme `tests/test_gui_sondes.py`.

## ⚠ MISE À JOUR lot 40 (2026-09-06) — le point 1 ci-dessus EST LEVÉ, et remplacé

Le mainteneur a décidé d'armer la vérification. La moitié 1 du garde-fou — « le `config.yaml`
publié laisse `maj.verifier` à `false` » — **ne décrit plus ce que le dépôt veut**, et les deux
tests qui la vérifiaient sont donc RÉÉCRITS, pas assouplis : ils affirment maintenant
l'inverse, avec la même exigence (sur `git show HEAD:config.yaml`, pas sur le fichier de
travail).

**La moitié 2 ne bouge pas d'une ligne**, et c'est elle qui vaut : `maj.verifier: false`
continue de garantir qu'aucun octet ne part, et c'est toujours vérifié en donnant un `httpx`
dont le `get` lève. Ce qui a changé est le défaut livré, pas la capacité de couper.

Ce que ce lot ajoute à protéger :

- **rien ne s'installe hors gel** — `installer()` refuse, et le test le vérifie sans lancer
  quoi que ce soit ;
- **une empreinte qui ne correspond pas n'installe rien**, et le fichier est effacé ;
- **un JSON de release hostile ne fait pas lever** la fonction dont tout le contrat est de ne
  jamais lever.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest
import yaml

from core import maj
from core.version import __version__

RACINE = Path(__file__).resolve().parent.parent


class _RefusDAppeler(AssertionError):
    """Levée si quoi que ce soit tente une requête alors que la vérification est désarmée."""


@pytest.fixture
def httpx_qui_refuse(monkeypatch):
    faux = type(sys)("httpx")
    faux.get = lambda *a, **k: (_ for _ in ()).throw(
        _RefusDAppeler(f"appel réseau interdit : {a} {k}"))
    monkeypatch.setitem(sys.modules, "httpx", faux)
    return faux


# --------------------------------------------------------------------------- #
#  Désarmé par défaut — et le fichier PUBLIÉ, pas celui de travail
# --------------------------------------------------------------------------- #

def test_le_defaut_du_depot_est_arme():
    """⚠ **Ce test affirmait l'inverse jusqu'au lot 40**, et il n'est pas assoupli : il est
    retourné. Le motif de la levée est écrit dans `config.yaml` au-dessus de la clé et dans
    l'en-tête de `core/maj.py` — « 100 % local » porte sur les ŒUVRES, et un `GET` anonyme sur
    une URL publique n'en dit rien."""
    config = yaml.safe_load((RACINE / "config.yaml").read_text(encoding="utf-8"))
    assert config["maj"]["verifier"] is True
    assert maj.armee(config) is True


def test_le_motif_de_la_levee_est_ecrit_a_cote_de_la_cle():
    """⚠ Un défaut qui se renverse sans que le fichier dise pourquoi est un défaut qu'on
    renversera encore. La règle §5 bis du dépôt demande un bloc DATÉ qui lève l'affirmation
    précédente, et le laisse lisible."""
    texte = (RACINE / "config.yaml").read_text(encoding="utf-8")
    assert "MISE À JOUR 2026-09-06, lot 40" in texte
    # L'ancienne affirmation est toujours là, au-dessus : elle est levée, pas effacée.
    assert "verifier: false" in texte or "`verifier: false` par défaut" in texte


def test_le_config_publie_arme_la_verification():
    """⚠ Sur `git show HEAD:config.yaml`. Le lot 27 a livré un `config.yaml` de travail qui
    armait une brique ; le fichier du disque n'est donc pas une preuve suffisante — dans un
    sens comme dans l'autre.

    ⚠ **Ce test est vert avant ET après le commit du lot 40** : il saute tant que `HEAD` est
    antérieur au lot, plutôt que d'échouer sur un commit qui ne pouvait pas le satisfaire.
    Sans cela il serait rouge au moment même où on le livre, ce qui apprend zéro chose."""
    sortie = subprocess.run(["git", "show", "HEAD:config.yaml"], cwd=RACINE,
                            capture_output=True, text=True, encoding="utf-8")
    if sortie.returncode != 0:                     # pragma: no cover — hors dépôt git
        pytest.skip("pas de dépôt git ici")
    publie = yaml.safe_load(sortie.stdout) or {}
    if "MISE À JOUR 2026-09-06, lot 40" not in sortie.stdout:
        pytest.skip("HEAD est antérieur au lot 40 — la levée n'y est pas encore")
    assert maj.armee(publie) is True, publie.get("maj")


def test_couper_reste_possible_et_coupe_vraiment(httpx_qui_refuse):
    """⚠ **La moitié du garde-fou qui NE BOUGE PAS.** Armer par défaut n'aurait aucune valeur
    si l'interrupteur n'existait plus : `verifier: false` continue de garantir qu'aucun octet
    ne part, et le double lèverait si la requête partait."""
    assert maj.armee({"maj": {"verifier": False}}) is False
    assert maj.verifier({"maj": {"verifier": False}}).detail == "désarmée"


def test_une_cle_absente_vaut_desarme():
    """Une installation antérieure au lot 37 n'a pas la section `maj:`. Lui faire faire un
    appel réseau parce qu'elle n'a rien dit serait l'inverse d'un opt-in."""
    assert maj.armee({}) is False
    assert maj.armee({"maj": {}}) is False


def test_desarme_aucun_appel_n_est_tente(httpx_qui_refuse):
    """LE test du critère 12 : le double lèverait si la requête partait."""
    resultat = maj.verifier({"maj": {"verifier": False}})
    assert resultat.arme is False
    assert resultat.detail == "désarmée"
    assert resultat.version == ""


def test_desarme_la_phrase_le_dit_a_l_humain():
    phrase = maj.verifier({}).phrase()
    assert "désarmée" in phrase
    assert "Rien ne sort de cette machine" in phrase


# --------------------------------------------------------------------------- #
#  Armé — ce qui part, et ce qui n'en part pas
# --------------------------------------------------------------------------- #

def _httpx_double(monkeypatch, etiquette: str, capture: dict):
    faux = type(sys)("httpx")

    class _Reponse:
        # ⚠ Ajouté au lot 40, et ce n'est pas une commodité : `verifier()` regarde le code de
        # statut AVANT `raise_for_status`, parce qu'un 404 y est traité comme une absence de
        # release et non comme une erreur. Un double qui n'aurait pas de `status_code` ne
        # serait plus un double fidèle d'une `httpx.Response`, qui en a toujours un.
        status_code = 200

        def raise_for_status(self):
            return None

        def json(self):
            return {"tag_name": etiquette}

    def _get(url, **kwargs):
        capture["url"] = url
        capture.update(kwargs)
        return _Reponse()

    faux.get = _get
    monkeypatch.setitem(sys.modules, "httpx", faux)


def test_arme_une_version_plus_recente_est_signalee(monkeypatch):
    capture: dict = {}
    _httpx_double(monkeypatch, "v99.0.0", capture)
    resultat = maj.verifier({"maj": {"verifier": True}})
    assert resultat.arme and resultat.disponible
    assert resultat.version == "99.0.0"
    assert "99.0.0" in resultat.phrase()


def test_arme_la_version_courante_ne_signale_rien(monkeypatch):
    _httpx_double(monkeypatch, f"v{__version__}", {})
    resultat = maj.verifier({"maj": {"verifier": True}})
    assert resultat.arme and not resultat.disponible
    assert "dernière version" in resultat.phrase()


def test_la_requete_ne_porte_ni_identifiant_ni_version(monkeypatch):
    """⚠ L'agent utilisateur est une CONSTANTE. Y mettre la version installée serait déjà de la
    télémétrie : le serveur saurait quelle version tourne ici."""
    capture: dict = {}
    _httpx_double(monkeypatch, "v1.0.0", capture)
    maj.verifier({"maj": {"verifier": True}})
    entetes = capture.get("headers") or {}
    assert entetes == {"User-Agent": maj.AGENT}
    assert __version__ not in maj.AGENT
    assert "data" not in capture and "json" not in capture and "params" not in capture


def test_un_reseau_qui_tombe_ne_leve_jamais(monkeypatch):
    faux = type(sys)("httpx")
    faux.get = lambda *a, **k: (_ for _ in ()).throw(TimeoutError("injoignable"))
    monkeypatch.setitem(sys.modules, "httpx", faux)
    resultat = maj.verifier({"maj": {"verifier": True}})
    assert resultat.arme and not resultat.disponible
    assert resultat.detail == "TimeoutError"
    assert "impossible" in resultat.phrase()


# --------------------------------------------------------------------------- #
#  La comparaison
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("publiee,installee,attendu", [
    ("2.31.0", "2.30.0", True),
    ("2.30.0", "2.30.0", False),
    ("2.29.0", "2.30.0", False),
    # ⚠ Le cas qui motive la comparaison sur trois entiers : en lexicographique,
    # « 2.9.0 » > « 2.10.0 ».
    ("2.10.0", "2.9.0", True),
    ("2.9.0", "2.10.0", False),
    ("", "2.30.0", False),
    ("pas-un-numero", "2.30.0", False),
])
def test_la_comparaison_est_numerique(publiee, installee, attendu):
    assert maj.plus_recente(publiee, installee) is attendu


def test_la_cle_est_connue_du_schema():
    """Une clé absente du schéma est signalée « inconnue » par `--check`, et lue avec sa valeur
    par défaut : la vérification serait donc muette et le message trompeur."""
    from core.config_schema import CLES_CONNUES
    assert {"maj", "maj.verifier", "maj.url", "maj.page"} <= CLES_CONNUES


# --------------------------------------------------------------------------- #
#  Lot 40 — les assets, l'empreinte, le refus d'installer hors gel
# --------------------------------------------------------------------------- #

def _release(monkeypatch, charge: dict, statut: int = 200):
    faux = type(sys)("httpx")

    class _Reponse:
        status_code = statut
        headers: dict = {}

        def raise_for_status(self):
            if statut >= 400:
                raise RuntimeError(f"HTTP {statut}")

        def json(self):
            return charge

    faux.get = lambda url, **k: _Reponse()
    monkeypatch.setitem(sys.modules, "httpx", faux)


CHARGE = {
    "tag_name": "v99.0.0",
    "assets": [
        {"name": "Angelith-99.0.0-windows-x64-setup.exe", "size": 306242994,
         "browser_download_url": "https://example.invalid/setup.exe"},
        {"name": "SHA256SUMS.txt", "size": 105,
         "browser_download_url": "https://example.invalid/SHA256SUMS.txt"},
    ],
}


def test_les_assets_sont_lus(monkeypatch):
    _release(monkeypatch, CHARGE)
    resultat = maj.verifier({"maj": {"verifier": True}})
    assert len(resultat.assets) == 2
    assert resultat.installeur().nom.endswith("-setup.exe")
    assert resultat.installeur().taille == 306242994
    assert resultat.sommes().nom == maj.NOM_SOMMES


def test_une_release_sans_asset_ne_promet_rien(monkeypatch):
    """⚠ **C'est le cas de TOUTES les releases publiées avant ce lot** : `publication.yml` en
    créait sans aucun fichier. L'appelant doit voir `None`, pas une exception."""
    _release(monkeypatch, {"tag_name": "v99.0.0"})
    resultat = maj.verifier({"maj": {"verifier": True}})
    assert resultat.disponible and resultat.assets == ()
    assert resultat.installeur() is None and resultat.sommes() is None


@pytest.mark.parametrize("assets", [
    [None],
    ["pas un dictionnaire"],
    [{"name": "x.exe"}],                                    # pas d'URL
    [{"browser_download_url": "https://example.invalid/x"}],  # pas de nom
    [{"name": "a-setup.exe", "browser_download_url": "u", "size": "gros"}],
])
def test_un_json_hostile_ne_fait_pas_lever(monkeypatch, assets):
    """Rien de ce JSON n'est de confiance : il vient du réseau. Une fonction dont tout le
    contrat est de ne jamais lever ne peut pas se permettre un `int(None)`."""
    _release(monkeypatch, {"tag_name": "v99.0.0", "assets": assets})
    resultat = maj.verifier({"maj": {"verifier": True}})
    assert resultat.arme is True


def test_un_404_n_est_pas_une_erreur_mais_une_absence(monkeypatch):
    """⚠ **C'est la réponse RÉELLE du miroir au 2026-09-06** (404 en 0,72 s, mesuré) : il est
    privé jusqu'à la candidature NLnet. Sur une vérification désormais armée par défaut,
    « Vérification impossible : HTTPStatusError » serait la première phrase que tout le monde
    lirait, et elle n'apprendrait rien."""
    _release(monkeypatch, {"message": "Not Found"}, statut=404)
    resultat = maj.verifier({"maj": {"verifier": True}})
    assert resultat.arme and not resultat.disponible
    assert resultat.detail == "aucune version n'est publiée"
    assert "publiée" in resultat.phrase()


# --------------------------------------------------------------------------- #
#  L'empreinte
# --------------------------------------------------------------------------- #

SOMMES = ("72a795885ccfc37bef8daa500ff7c3e24f586ccbac4b0da0e133caeb2ae32670  "
          "Angelith-2.31.0-windows-x64-setup.exe\n")


def test_l_empreinte_attendue_se_lit_au_format_coreutils():
    assert (maj.empreinte_attendue(SOMMES, "Angelith-2.31.0-windows-x64-setup.exe")
            == "72a795885ccfc37bef8daa500ff7c3e24f586ccbac4b0da0e133caeb2ae32670")


def test_un_nom_absent_du_fichier_rend_une_chaine_vide():
    """⚠ Et l'appelant doit alors NE PAS télécharger : un installeur qu'on ne peut pas vérifier
    vaut moins qu'un lien, parce qu'il aurait l'air vérifié."""
    assert maj.empreinte_attendue(SOMMES, "autre-chose.exe") == ""


@pytest.mark.parametrize("ligne", [
    "",
    "# un commentaire",
    "une-seule-colonne",
])
def test_les_lignes_qui_ne_sont_pas_des_empreintes_sont_ignorees(ligne):
    assert maj.empreinte_attendue(ligne + "\n" + SOMMES,
                                  "Angelith-2.31.0-windows-x64-setup.exe")


def test_l_etoile_du_mode_binaire_ne_casse_pas_la_comparaison():
    """`sha256sum -b` écrit `<hex> *<nom>`. Le fichier du dépôt est écrit par
    `tools/verifier_gel.py`, mais rien n'oblige un contributeur à s'en servir."""
    texte = "abc  *mon-fichier.exe\n"
    assert maj.empreinte_attendue(texte, "mon-fichier.exe") == "abc"


def test_un_nom_avec_des_espaces_survit():
    """⚠ Le motif du `split(None, 1)` : un `split()` sur tous les blancs perdrait ce nom, et
    une vérification d'intégrité qui échoue en silence est pire que pas de vérification."""
    texte = "abc  mon fichier.exe\n"
    assert maj.empreinte_attendue(texte, "mon fichier.exe") == "abc"


def test_l_empreinte_d_un_fichier_est_celle_de_hashlib(tmp_path):
    import hashlib
    fichier = tmp_path / "x.bin"
    fichier.write_bytes(b"angelith" * 1000)
    assert maj.empreinte(fichier) == hashlib.sha256(b"angelith" * 1000).hexdigest()


# --------------------------------------------------------------------------- #
#  Le téléchargement, et ce qu'il laisse derrière lui
# --------------------------------------------------------------------------- #

def _httpx_flux(monkeypatch, morceaux: list[bytes], taille: int | None = None):
    faux = type(sys)("httpx")

    class _Flux:
        headers = {"content-length": str(taille if taille is not None
                                         else sum(len(m) for m in morceaux))}

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def raise_for_status(self):
            return None

        def iter_bytes(self, taille_bloc):
            yield from morceaux

    faux.stream = lambda methode, url, **k: _Flux()
    monkeypatch.setitem(sys.modules, "httpx", faux)


def test_le_telechargement_ecrit_le_fichier_et_rend_la_progression(monkeypatch, tmp_path):
    _httpx_flux(monkeypatch, [b"aa", b"bb", b"cc"])
    vus: list[tuple[int, int]] = []
    chemin = maj.telecharger(maj.Asset("x.exe", "https://example.invalid/x", 6),
                             tmp_path / "x.exe", progres=lambda lus, total: vus.append(
                                 (lus, total)))
    assert chemin.read_bytes() == b"aabbcc"
    assert vus == [(2, 6), (4, 6), (6, 6)]


def test_une_annulation_n_est_pas_une_erreur_et_ne_laisse_rien(monkeypatch, tmp_path):
    """⚠ Deux affirmations, et la seconde est la vraie : un fichier PARTIEL qui porterait le
    nom final serait vérifié, refusé, et resterait sur le disque à ressembler à un
    installeur."""
    _httpx_flux(monkeypatch, [b"aa", b"bb", b"cc"])
    with pytest.raises(maj.Annule):
        maj.telecharger(maj.Asset("x.exe", "u", 6), tmp_path / "x.exe", arret=lambda: True)
    assert list(tmp_path.iterdir()) == []


def test_un_reseau_qui_tombe_en_cours_ne_laisse_pas_de_partiel(monkeypatch, tmp_path):
    def _morceaux():
        yield b"aa"
        raise TimeoutError("coupé")

    faux = type(sys)("httpx")

    class _Flux:
        headers: dict = {}

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def raise_for_status(self):
            return None

        def iter_bytes(self, taille_bloc):
            return _morceaux()

    faux.stream = lambda methode, url, **k: _Flux()
    monkeypatch.setitem(sys.modules, "httpx", faux)
    with pytest.raises(TimeoutError):
        maj.telecharger(maj.Asset("x.exe", "u", 0), tmp_path / "x.exe")
    assert list(tmp_path.iterdir()) == []


def test_sans_taille_annoncee_la_progression_rend_zero(monkeypatch, tmp_path):
    """`total` vaut `0` quand ni l'API ni l'en-tête ne l'ont donné : on affiche ce qui est lu,
    sans inventer de pourcentage."""
    _httpx_flux(monkeypatch, [b"aa"], taille=0)
    vus: list[tuple[int, int]] = []
    maj.telecharger(maj.Asset("x.exe", "u", 0), tmp_path / "x.exe",
                    progres=lambda lus, total: vus.append((lus, total)))
    assert vus == [(2, 0)]


# --------------------------------------------------------------------------- #
#  ⚠ Le refus d'installer hors gel — et AUCUN processus n'est lancé
# --------------------------------------------------------------------------- #

def test_hors_gel_rien_n_est_installe(tmp_path, monkeypatch):
    """⚠ Lancer un installeur depuis un dépôt git remplacerait un arbre de travail par une
    installation. Le test vérifie DEUX choses : que ça lève, et qu'aucun `Popen` n'a eu lieu —
    la première sans la seconde ne prouverait rien sur l'ordre des deux."""
    import core.installation as installation
    monkeypatch.setattr(installation, "gele", lambda: False)
    lances = []
    import subprocess as sp
    monkeypatch.setattr(sp, "Popen", lambda *a, **k: lances.append(a))
    faux = tmp_path / "setup.exe"
    faux.write_bytes(b"MZ")
    with pytest.raises(RuntimeError) as err:
        maj.installer(faux)
    assert "git pull" in str(err.value)
    assert lances == []


def test_gele_un_fichier_absent_est_refuse_avant_tout_lancement(tmp_path, monkeypatch):
    import core.installation as installation
    monkeypatch.setattr(installation, "gele", lambda: True)
    lances = []
    import subprocess as sp
    monkeypatch.setattr(sp, "Popen", lambda *a, **k: lances.append(a))
    with pytest.raises(FileNotFoundError):
        maj.installer(tmp_path / "absent.exe")
    assert lances == []


def test_un_depot_sans_release_ne_dit_pas_verification_impossible():
    """⚠ **Le cas NOMINAL d'un dépôt public tant qu'aucun tag n'y a été poussé**, donc la
    première phrase que tout le monde lit. « Vérification impossible : aucune version n'est
    publiée » se contredisait : la vérification a parfaitement abouti, c'est la réponse qui
    est « il n'y en a pas »."""
    resultat = maj.Resultat(arme=True, detail=maj.SANS_RELEASE)
    phrase = resultat.phrase()
    assert "impossible" not in phrase
    assert "Aucune version n'est encore publiée" in phrase
    assert resultat.page in phrase


def test_un_vrai_echec_reseau_dit_toujours_impossible():
    """Iso : la correction ci-dessus ne doit pas avaler les échecs qui en sont vraiment."""
    assert "impossible" in maj.Resultat(arme=True, detail="TimeoutError").phrase()
