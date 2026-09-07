# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Alexandre Tournel

"""Les gestes réparateurs (`core/reparations.py`) — **et surtout ce qu'ils n'ont pas le droit
de faire**.

Ce fichier porte quatre des douze critères du `PLAN-36`, et ce sont les quatre qui engagent le
projet plutôt que son confort :

- **critère 5** — aucun téléchargement ne part sans clic explicite ; aucun pendant un run ;
  chacun affiche la licence **avant** et enregistre URL, date, taille et SHA-256 après ;
- **critère 6** — ⚠ **aucun logiciel système n'est installé par l'application.** Un test lit le
  code de `core/reparations.py` par `ast` et vérifie qu'aucun chemin n'appelle un installateur
  ni un gestionnaire de paquets ;
- **critère 7** — un fichier de poids partiel est détecté avant usage, et le geste de reprise
  est proposé ;
- **critère 10** — la page « À propos » liste les licences des poids réellement présents, lues
  dans les fichiers de provenance.

Aucun test ici n'ouvre de socket : les téléchargements sont doublés, et c'est le point — un
test qui téléchargerait 104 Mo serait un test qu'on désactive.
"""
from __future__ import annotations

import ast
import json
from pathlib import Path

import pytest

from core import provenance
from core import reparations as rep
# ⚠ Importé pour son EFFET : il enregistre les réparations de la brique manga dans le catalogue
# de `core/reparations.py`. `core` ne peut pas le faire lui-même — il n'importe aucune brique
# (`tests/test_imports_briques.py`), et ce test-ci vérifie justement ce partage.
from manga import reparations as rep_manga  # noqa: F401

RACINE = Path(__file__).resolve().parent.parent

#: Les deux modules qui portent des gestes réparateurs. ⚠ Les deux sont scannés : une règle
#: qui ne vaudrait que pour le socle laisserait la brique libre de lancer un installateur.
MODULES_DE_REPARATION = ("core/reparations.py", "manga/reparations.py")


# --------------------------------------------------------------------------- #
#  Critère 6 — Angelith n'installe aucun logiciel système
# --------------------------------------------------------------------------- #

#: Les gestionnaires de paquets et installateurs que le code ne doit **jamais** appeler.
#: ⚠ Ce n'est pas une liste de mots interdits dans le fichier : `winget install …` figure bien
#: dans le catalogue, comme **commande copiable** proposée à l'utilisateur, et c'est ce que le
#: plan autorise (« un lien, une commande copiable, une revérification »). Ce qui est interdit
#: est de l'EXÉCUTER — d'où un test qui regarde les appels, pas les chaînes.
INSTALLATEURS = frozenset({
    "winget", "choco", "chocolatey", "scoop", "apt", "apt-get", "dnf", "yum", "pacman",
    "zypper", "brew", "port", "msiexec", "installer", "snap", "flatpak", "npm", "yarn",
})


def _appels_de_sous_processus(source: str) -> list[ast.Call]:
    """Tout appel qui peut LANCER un programme : `subprocess.*`, `os.system`, `os.popen`,
    `os.exec*`, `os.spawn*`, `shutil.which` exclu (il ne lance rien)."""
    arbre = ast.parse(source)
    trouves: list[ast.Call] = []
    for noeud in ast.walk(arbre):
        if not isinstance(noeud, ast.Call):
            continue
        cible = noeud.func
        if isinstance(cible, ast.Attribute):
            module = getattr(cible.value, "id", "")
            if module == "subprocess":
                trouves.append(noeud)
            elif module == "os" and (cible.attr in {"system", "popen"}
                                     or cible.attr.startswith(("exec", "spawn"))):
                trouves.append(noeud)
    return trouves


def _litteraux(noeud: ast.AST) -> list[str]:
    return [n.value for n in ast.walk(noeud)
            if isinstance(n, ast.Constant) and isinstance(n.value, str)]


@pytest.mark.parametrize("module", MODULES_DE_REPARATION)
def test_aucun_chemin_de_reparation_n_appelle_un_installateur_ni_un_gestionnaire_de_paquets(
        module):
    """⚠ **Critère 6 du `PLAN-36`, et la ligne à ne pas franchir.**

    « Angelith n'installe aucun logiciel système. Ni Pandoc, ni un gestionnaire de paquets, ni
    un service. » Le `PLAN-30` avait déjà tranché le principe voisin pour ComfyUI.

    Le test regarde les APPELS de sous-processus et leurs littéraux, pas les chaînes du
    fichier : une commande affichée à l'utilisateur est autorisée, l'exécuter ne l'est pas."""
    source = (RACINE / module).read_text(encoding="utf-8")
    for appel in _appels_de_sous_processus(source):
        for texte in _litteraux(appel):
            premier = Path(texte.split()[0]).stem.lower() if texte.split() else ""
            assert premier not in INSTALLATEURS, (
                f"{module} lance « {texte} » : Angelith n'installe aucun logiciel système.")


def test_le_socle_ne_lance_aucun_sous_processus():
    """`core/reparations.py` ne porte que le vocabulaire et des entrées déclaratives : il n'a
    rien à exécuter, et son code le montre."""
    source = (RACINE / "core" / "reparations.py").read_text(encoding="utf-8")
    assert _appels_de_sous_processus(source) == []


def test_le_seul_sous_processus_lance_est_le_script_de_polices():
    """Et il est nommé, pour qu'un ajout futur ne passe pas inaperçu.

    ⚠ `tools/installer_polices.ps1` **enregistre** des polices pour l'utilisateur courant —
    aucun droit administrateur, aucun autre compte touché, `-Desinstaller` remet tout en
    place. Enregistrer une police n'installe aucun logiciel : rien ne s'exécute, rien ne
    devient un service, et le geste est réversible."""
    source = (RACINE / "manga" / "reparations.py").read_text(encoding="utf-8")
    appels = _appels_de_sous_processus(source)
    assert len(appels) == 1, f"{len(appels)} appel(s) de sous-processus, un seul est prévu"
    litteraux = _litteraux(appels[0])
    assert "powershell" in litteraux
    assert "-ExecutionPolicy" in litteraux and "Bypass" in litteraux


def test_le_socle_n_importe_aucune_brique_pour_reparer():
    """⚠ **La raison d'être du registre.** `core` est le socle, il ne remonte jamais — et
    récupérer un poids de détection demande `manga.models`. Le vocabulaire reste ici, le geste
    appartient à la brique. `tests/test_imports_briques.py` garde la règle générale ; ce test
    la garde à l'endroit précis où le lot 36 a failli l'enfreindre."""
    source = (RACINE / "core" / "reparations.py").read_text(encoding="utf-8")
    arbre = ast.parse(source)
    for noeud in ast.walk(arbre):
        noms: list[str] = []
        if isinstance(noeud, ast.Import):
            noms = [alias.name for alias in noeud.names]
        elif isinstance(noeud, ast.ImportFrom) and not noeud.level:
            noms = [noeud.module or ""]
        for nom in noms:
            assert nom.split(".")[0] not in {"manga", "pipeline", "scan", "illustration", "gui"}, nom


def test_une_reparation_de_brique_est_inconnue_tant_que_son_module_n_est_pas_importe():
    """⚠ Et c'est EXACT, pas un défaut : on ne répare pas une brique qu'on n'a pas chargée. Le
    message de refus le dit, pour qu'un appelant sache quoi faire."""
    with pytest.raises(rep.RefusDeReparer) as echec:
        rep.executer("une_reparation_qui_n_existe_pas", {}, consentement=True)
    assert "module de réparation n'a peut-être pas été importé" in str(echec.value)


def test_les_reparations_de_classe_utilisateur_ne_sont_jamais_automatiques():
    """Pandoc, `unrar`, ComfyUI, WeasyPrint : un lien et une commande, jamais un bouton."""
    for reparation in rep.par_classe(rep.UTILISATEUR):
        assert reparation.automatique is False, reparation.identifiant
        with pytest.raises(rep.RefusDeReparer):
            rep.executer(reparation.identifiant, {}, consentement=True)


def test_les_reparations_hors_perimetre_disent_ce_qui_manque_et_s_arretent_la():
    for reparation in rep.par_classe(rep.HORS_PERIMETRE):
        assert reparation.automatique is False
        assert reparation.note, reparation.identifiant
        with pytest.raises(rep.RefusDeReparer):
            rep.executer(reparation.identifiant, {}, consentement=True)


# --------------------------------------------------------------------------- #
#  Critère 5 — le consentement, le run, et la licence AVANT
# --------------------------------------------------------------------------- #

def test_aucun_telechargement_ne_part_sans_consentement_explicite():
    """⚠ « Pas de préparation automatique au premier lancement : un premier lancement qui
    consomme plusieurs gigaoctets sans demander est un défaut, quelle que soit l'intention. »"""
    with pytest.raises(rep.RefusDeReparer) as echec:
        rep.executer("poids_detection", {}, consentement=False)
    assert "clic explicite" in str(echec.value)


def test_aucun_telechargement_ne_part_pendant_un_run():
    """⚠ « Un run de nuit qui se met à télécharger 2 Go n'est plus le run qu'on a lancé. »"""
    with pytest.raises(rep.RefusDeReparer) as echec:
        rep.executer("poids_detection", {}, consentement=True, run_en_cours=True)
    assert "run est en cours" in str(echec.value)


def test_le_refus_pendant_un_run_passe_AVANT_toute_lecture_de_config():
    """Aucun ordre d'évaluation malheureux ne doit pouvoir contourner les deux refus : on les
    vérifie avec une config qui ferait planter tout le reste."""
    with pytest.raises(rep.RefusDeReparer):
        rep.executer("poids_detection", None, consentement=True, run_en_cours=True)


def test_la_consigne_affiche_la_licence_la_source_et_la_taille_AVANT_le_clic():
    """⚠ « Une licence montrée après le téléchargement ne sert à rien. »"""
    reparation = rep.par_identifiant("poids_detection")
    consigne = reparation.consigne()
    assert "Licence :" in consigne
    assert "Source primaire :" in consigne
    assert "Mo" in consigne
    assert "ne redistribue ni n'héberge aucun poids" in consigne


def test_le_poids_non_redistribuable_le_dit_dans_sa_consigne():
    """⚠ Le détecteur de texte est GPL-3.0 **et** entraîné pour partie sur Manga109-s, qui a
    ses propres conditions d'usage. Il se récupère chez son éditeur, jamais chez nous."""
    consigne = rep.par_identifiant("poids_texte").consigne()
    assert "Manga109" in consigne
    assert "jamais depuis un miroir du projet" in consigne


def test_une_reparation_inconnue_est_refusee_et_le_dit():
    with pytest.raises(rep.RefusDeReparer):
        rep.executer("licorne", {}, consentement=True)


def test_chaque_reparation_declare_une_classe_connue_et_une_phrase():
    for reparation in rep.catalogue():
        assert reparation.classe in rep.CLASSES, reparation.identifiant
        assert reparation.quoi, reparation.identifiant
        if reparation.classe == rep.RECUPERABLE:
            assert reparation.licence, reparation.identifiant


def test_la_taille_lisible_porte_son_ordre_de_grandeur():
    assert rep.par_identifiant("poids_detection").taille_lisible.startswith("~")
    assert rep.Reparation("x", "X", rep.RECUPERABLE, quoi="").taille_lisible \
        == "taille inconnue"


# --------------------------------------------------------------------------- #
#  Critère 7 — le fichier partiel
# --------------------------------------------------------------------------- #

def test_un_fichier_tronque_est_detecte_avant_usage(tmp_path):
    """⚠ « Un fichier partiel doit être détecté (par sa taille et son empreinte), pas chargé
    et laissé planter dans `onnxruntime`. » Le message d'onnxruntime est obscur, il revient à
    chaque relance, et rien n'y dit qu'il suffit de supprimer le fichier."""
    poids = tmp_path / "detecteur.onnx"
    poids.write_bytes(b"x" * 1000)
    etat = rep.etat_fichier(poids, octets_attendus=100_000)
    assert etat.present is True
    assert etat.partiel is True
    assert etat.utilisable is False
    assert "incomplet" in etat.motif


def test_un_fichier_vide_est_partiel_meme_sans_taille_attendue(tmp_path):
    poids = tmp_path / "vide.onnx"
    poids.write_bytes(b"")
    assert rep.etat_fichier(poids).partiel is True


def test_un_part_laisse_par_une_coupure_est_signale(tmp_path):
    """`manga/models.telecharger` écrit dans un `.part` renommé en dernier : un `.part` qui
    survit est la signature d'un téléchargement interrompu, et le geste de reprise est là."""
    poids = tmp_path / "detecteur.onnx"
    (tmp_path / "detecteur.onnx.part").write_bytes(b"xxx")
    etat = rep.etat_fichier(poids, octets_attendus=100_000)
    assert etat.present is False
    assert etat.reste_un_part is True
    assert "refait proprement" in etat.motif


def test_un_fichier_entier_sans_fiche_le_dit_sans_lui_inventer_de_licence(tmp_path):
    poids = tmp_path / "detecteur.onnx"
    poids.write_bytes(b"x" * 200_000)
    etat = rep.etat_fichier(poids, octets_attendus=100_000)
    assert etat.utilisable is True
    assert etat.concorde is None
    assert "sans fiche de provenance" in etat.motif


def test_une_empreinte_qui_diverge_est_signalee_mais_n_interdit_pas_l_usage(tmp_path):
    """⚠ Même règle que `manga/models.py` : « un dépôt amont qui republie ses poids ne doit pas
    bloquer le pipeline, seulement faire dire que le fichier n'est plus celui d'origine »."""
    poids = tmp_path / "detecteur.onnx"
    poids.write_bytes(b"x" * 1000)
    provenance.ecrire(poids, url="https://exemple/x", licence="Apache-2.0")
    poids.write_bytes(b"y" * 1000)
    etat = rep.etat_fichier(poids)
    assert etat.concorde is False
    assert etat.utilisable is True, "une empreinte différente n'est pas une troncature"


# --------------------------------------------------------------------------- #
#  La provenance — critères 5 et 10
# --------------------------------------------------------------------------- #

def test_la_fiche_porte_url_date_taille_sha256_et_licence(tmp_path):
    poids = tmp_path / "detecteur.onnx"
    poids.write_bytes(b"abc")
    fiche = provenance.ecrire(poids, url="https://exemple/detecteur.onnx",
                              licence="AGPL-3.0", licence_url="https://exemple/licence")
    assert fiche.url == "https://exemple/detecteur.onnx"
    assert fiche.octets == 3
    assert len(fiche.sha256) == 64
    assert fiche.date.count("-") == 2
    assert fiche.licence == "AGPL-3.0"
    assert fiche.version_angelith


def test_la_fiche_mesure_le_fichier_plutot_que_de_croire_le_serveur(tmp_path):
    """⚠ « `Content-Length` peut mentir, et un téléchargement coupé produit un fichier court
    que le serveur avait pourtant annoncé complet. » La fiche décrit un fait, pas une
    intention."""
    poids = tmp_path / "x.onnx"
    poids.write_bytes(b"1234567890")
    fiche = provenance.ecrire(poids, url="https://exemple/x", licence="Apache-2.0")
    assert fiche.octets == poids.stat().st_size


def test_une_fiche_corrompue_rend_None_plutot_que_de_lever(tmp_path):
    """⚠ Cette fonction sert la page « À propos » : une fiche corrompue doit produire
    « provenance inconnue », jamais une fenêtre qui ne s'ouvre pas."""
    poids = tmp_path / "x.onnx"
    poids.write_bytes(b"x")
    provenance.chemin_fiche(poids).write_text("{ pas du json", encoding="utf-8")
    assert provenance.lire(poids) is None


def test_une_fiche_sans_empreinte_est_refusee(tmp_path):
    poids = tmp_path / "x.onnx"
    poids.write_bytes(b"x")
    provenance.chemin_fiche(poids).write_text(json.dumps({"fichier": "x.onnx"}),
                                              encoding="utf-8")
    assert provenance.lire(poids) is None


def test_l_inventaire_ne_liste_que_ce_qui_est_reellement_la(tmp_path):
    """⚠ **Critère 10.** « Les licences des poids réellement présents », pas la liste théorique
    de ce que le projet sait télécharger."""
    (tmp_path / "vide").mkdir()
    poids = tmp_path / "a.onnx"
    poids.write_bytes(b"x")
    provenance.ecrire(poids, url="https://exemple/a", licence="Apache-2.0")
    fiches = provenance.inventorier([tmp_path, tmp_path / "vide", tmp_path / "absent"])
    assert [f.fichier for f in fiches] == ["a.onnx"]
    assert "Apache-2.0" in fiches[0].resume()


def test_une_fiche_orpheline_est_ignoree(tmp_path):
    """Le disque a toujours raison : une fiche dont le poids a été supprimé ne crédite rien."""
    provenance.chemin_fiche(tmp_path / "parti.onnx").write_text(
        json.dumps({"fichier": "parti.onnx", "sha256": "0" * 64, "url": "", "date": "",
                    "octets": 1, "licence": "X"}), encoding="utf-8")
    assert provenance.inventorier([tmp_path]) == []


def test_concorde_rend_None_quand_il_n_y_a_rien_a_comparer(tmp_path):
    assert provenance.concorde(tmp_path / "absent.onnx") is None


# --------------------------------------------------------------------------- #
#  Le téléchargement, doublé — la fiche est écrite APRÈS, et elle est écrite
# --------------------------------------------------------------------------- #

def test_un_telechargement_reussi_ecrit_sa_fiche_de_provenance(tmp_path, monkeypatch):
    """⚠ **Critère 5, la seconde moitié.** Sans la fiche, un poids sur le disque n'a ni licence
    ni date, et la page « À propos » ne peut rien en dire d'exact."""
    cible = tmp_path / "manga_models" / "bubble_detector.onnx"
    dits: list[str] = []

    def _faux_telechargement(url, destination, **kw):
        Path(destination).parent.mkdir(parents=True, exist_ok=True)
        Path(destination).write_bytes(b"z" * 4096)
        return Path(destination)

    monkeypatch.setattr("manga.reparations.models.telecharger", _faux_telechargement)
    config = {"manga": {"detection": {"model_path": str(cible)}}}
    chemin = rep.executer("poids_detection", config, consentement=True, run_en_cours=False,
                          dire=dits.append)
    assert chemin == cible
    fiche = provenance.lire(cible)
    assert fiche is not None
    assert fiche.url == rep.par_identifiant("poids_detection").url
    assert fiche.octets == 4096
    assert "Licence de ce poids" in dits[0], "la licence doit être dite AVANT le transfert"


def test_un_fichier_partiel_est_ecarte_avant_de_retelecharger(tmp_path, monkeypatch):
    """Critère 7, second volet : le geste de reprise refait le fichier proprement."""
    cible = tmp_path / "bubble_detector.onnx"
    cible.write_bytes(b"x" * 10)

    def _faux_telechargement(url, destination, **kw):
        Path(destination).write_bytes(b"z" * 4096)
        return Path(destination)

    monkeypatch.setattr("manga.reparations.models.telecharger", _faux_telechargement)
    config = {"manga": {"detection": {"model_path": str(cible)}}}
    dits: list[str] = []
    rep.executer("poids_detection", config, consentement=True, dire=dits.append)
    assert cible.stat().st_size == 4096
    assert any("incomplet" in ligne for ligne in dits)


def test_le_poids_atterrit_a_l_endroit_que_la_brique_ira_LIRE(tmp_path, monkeypatch):
    """⚠ Un téléchargement qui réussit et un pipeline qui ne trouve rien serait le pire des
    deux mondes. La cible est la clé de config que `BubbleDetector.depuis_config` lit."""
    vus: list[Path] = []

    def _faux_telechargement(url, destination, **kw):
        vus.append(Path(destination))
        Path(destination).parent.mkdir(parents=True, exist_ok=True)
        Path(destination).write_bytes(b"z" * 4096)
        return Path(destination)

    monkeypatch.setattr("manga.reparations.models.telecharger", _faux_telechargement)
    voulu = tmp_path / "ailleurs" / "mon_detecteur.onnx"
    rep.executer("poids_detection", {"manga": {"detection": {"model_path": str(voulu)}}},
                 consentement=True)
    assert vus == [voulu]
