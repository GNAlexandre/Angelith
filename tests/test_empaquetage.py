# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Alexandre Tournel

"""Le `.spec`, l'installeur et les vérifications du gel — `PLAN-37` L37.3, L37.5, L37.7.

## Ce que ce fichier peut tenir, et ce qu'il ne peut pas

Il **ne construit pas** de gel : huit minutes et 390 Mo par exécution ne sont pas le prix d'une
boucle courte. Ce qui se construit, c'est le job de CI qui le fait ; ce qui se teste ici, ce
sont les **décisions écrites dans les fichiers** — et elles sont exactement celles qu'un lot
ultérieur pourrait défaire sans s'en rendre compte :

- `--onefile` refusé, et le motif présent dans le `.spec` ;
- l'installeur par UTILISATEUR, et sa désinstallation qui ne touche à aucune donnée ;
- le numéro de version qui vient de `core/version.py`, jamais d'une saisie ;
- les trois vérifications du gel, qui doivent **échouer** sur un relevé fautif — un garde-fou
  qui ne sait pas dire non est un garde-fou décoratif.

⚠ Le dernier point est le seul qui teste du COMPORTEMENT, et c'est le plus important : les trois
étapes de CI ne valent que si `tools/verifier_gel.py` sait rendre 1.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from core.version import __version__
from tools import verifier_gel

RACINE = Path(__file__).resolve().parent.parent
SPEC = RACINE / "angelith.spec"
ISS = RACINE / "installeur" / "angelith.iss"


# --------------------------------------------------------------------------- #
#  Le `.spec` — L37.3
# --------------------------------------------------------------------------- #

def test_le_spec_existe_et_produit_un_dossier():
    texte = SPEC.read_text(encoding="utf-8")
    assert "COLLECT(" in texte, "sans COLLECT, PyInstaller produit un fichier unique"


def test_onefile_est_refuse_et_le_motif_est_ecrit():
    """Critère 6 : « le refus de `--onefile` est motivé dans le `.spec` ». Un motif qui
    disparaît, c'est la décision qui se reprend sans qu'on sache pourquoi elle avait été
    prise."""
    texte = SPEC.read_text(encoding="utf-8")
    assert "onefile" in texte.lower()
    for mot in ("antivirus", "heuristique", "extract"):
        assert mot in texte.lower(), mot


def test_le_spec_n_active_pas_upx():
    """UPX compresse les sections du binaire, et une section compressée est un signal
    d'heuristique de plus — sur un projet qui a déjà refusé `--onefile` pour cette raison."""
    texte = SPEC.read_text(encoding="utf-8")
    assert "upx=True" not in texte
    assert "upx=False" in texte


def test_le_spec_ne_declare_aucune_dependance():
    """⚠ Le `.spec` n'est pas la place des dépendances (L37.2). Le jour où les deux listes
    divergent, c'est le gel qui manque un module — et le symptôme est un `ImportError` chez
    l'utilisateur, pas chez nous."""
    texte = SPEC.read_text(encoding="utf-8")
    debut = texte.index("IMPORTS_CACHES = [")
    bloc = texte[debut:texte.index("\n]", debut)]
    for interdit in ("PySide6", "numpy", "onnxruntime", "manga-ocr", "rapidocr", "openai"):
        assert interdit not in bloc, (
            f"{interdit} est déclaré dans le .spec : sa place est pyproject.toml")


def test_les_deux_executables_sont_declares():
    """Le fenêtré et le console. ⚠ Le second n'est pas un confort : sous Windows, un binaire
    lié en sous-système « fenêtre » n'a pas de sortie standard, et la CI ne pourrait donc lire
    aucune des trois vérifications."""
    texte = SPEC.read_text(encoding="utf-8")
    assert 'name="angelith-gui"' in texte and "console=False" in texte
    assert 'name="angelith-console"' in texte and "console=True" in texte


def test_le_spec_n_ecrit_pas_dans_le_dossier_des_oeuvres():
    """`build/` est le dossier des SORTIES du pipeline dans ce dépôt. Laisser PyInstaller y
    écrire mêlerait ses intermédiaires à des tomes qui coûtent des heures de GPU."""
    texte = SPEC.read_text(encoding="utf-8")
    assert "--workpath" in texte
    assert ".pyinstaller" in texte
    # ⚠ Depuis le lot 38, c'est `tools/geler.py` qui passe le `--workpath`, et la CI l'appelle.
    # Le vérifier ici plutôt que dans le YAML est ce qui rend la règle testable des deux côtés.
    outil = (RACINE / "tools" / "geler.py").read_text(encoding="utf-8")
    assert '"--workpath", TRAVAIL' in outil


def test_le_gitignore_couvre_les_sorties_d_empaquetage():
    texte = (RACINE / ".gitignore").read_text(encoding="utf-8")
    for motif in ("*.egg-info/", "dist/", ".pyinstaller/"):
        assert motif in texte, motif


# --------------------------------------------------------------------------- #
#  L'installeur — L37.5
# --------------------------------------------------------------------------- #

def _directives() -> list[str]:
    """Les lignes du `.iss` qui font quelque chose — commentaires exclus.

    ⚠ Le fichier EXPLIQUE pourquoi `{autopf}` est écarté ; un test qui lirait le texte brut
    échouerait sur l'explication du choix. Même piège que
    `tests/test_installation_chemins.py`, et même remède."""
    return [ln.strip() for ln in ISS.read_text(encoding="utf-8").splitlines()
            if ln.strip() and not ln.strip().startswith(";")]


def test_l_installeur_s_installe_par_utilisateur_sans_uac():
    directives = _directives()
    assert "PrivilegesRequired=lowest" in directives
    assert any(ln.startswith(r"DefaultDirName={localappdata}\Programs")
               for ln in directives), directives
    assert not [ln for ln in directives if "{autopf}" in ln or "{pf}" in ln], (
        "Program Files exigerait une élévation, et le dossier serait en lecture seule")


def test_la_desinstallation_ne_supprime_aucune_oeuvre():
    """Critère 10. La seule suppression proposée porte sur `%LOCALAPPDATA%\\Angelith` — les
    réglages —, jamais sur `Documents\\Angelith`, qui porte les tomes traduits."""
    directives = _directives()
    suppressions = [ln for ln in directives if "DelTree" in ln]
    assert len(suppressions) == 1, suppressions
    # Le chemin supprimé est celui, et le seul, que le code construit.
    cibles = [ln for ln in directives if "ExpandConstant(" in ln]
    assert len(cibles) == 1, cibles
    assert r"{localappdata}\Angelith" in cibles[0], cibles
    assert not [ln for ln in directives
                if "Documents" in ln and ("DelTree" in ln or "ExpandConstant" in ln)]
    # Et rien n'est supprimé en aveugle par la section dédiée.
    texte = ISS.read_text(encoding="utf-8")
    corps = texte[texte.index("[UninstallDelete]"):texte.index("[Code]")]
    assert not [ln for ln in corps.splitlines()
                if ln.strip() and not ln.strip().startswith((";", "["))], corps


def test_la_suppression_des_reglages_est_decochee_par_defaut():
    """`MB_DEFBUTTON2` : le bouton par défaut de la boîte est « Non ». Quelqu'un qui valide
    sans lire garde ses réglages."""
    texte = ISS.read_text(encoding="utf-8")
    assert "MB_DEFBUTTON2" in texte


def test_l_installeur_ne_saisit_jamais_sa_version():
    texte = ISS.read_text(encoding="utf-8")
    assert '#include "version.iss"' in texte
    assert "AppVersion={#MaVersion}" in texte
    assert __version__ not in texte, (
        "le numéro est écrit en dur dans le .iss : il vieillira en silence")


def test_le_fichier_de_version_de_l_installeur_est_a_jour():
    """Le garde-fou de la règle 5 de `tools/verifier_livraison.py`, vu de l'autre côté."""
    resultat = subprocess.run([sys.executable, "installeur/generer.py", "--verifier"],
                              cwd=RACINE, capture_output=True, text=True, encoding="utf-8")
    assert resultat.returncode == 0, resultat.stdout + resultat.stderr
    assert __version__ in (RACINE / "installeur/version.iss").read_text(encoding="utf-8")


def test_la_page_d_information_dit_ce_qui_n_est_pas_livre():
    """Étape 0.3 : « un installeur en un clic qui laisse cinq installations manuelles à faire
    doit le dire à l'écran 1, pas à l'écran 6 »."""
    texte = (RACINE / "installeur/avant-installation.txt").read_text(encoding="utf-8")
    for absent in ("poids de detection", "modele de langue", "Pandoc", "WeasyPrint",
                   "unrar", "ComfyUI", "AUCUNE oeuvre"):
        assert absent in texte, absent
    assert "InfoBeforeFile=avant-installation.txt" in ISS.read_text(encoding="utf-8")


def test_l_avertissement_smartscreen_est_annonce():
    """Critère 11, moitié « annoncé plutôt que découvert ». Sans signature, SmartScreen
    avertit ; le dire est la seule chose honnête à faire tant qu'aucun certificat n'existe."""
    texte = (RACINE / "installeur/avant-installation.txt").read_text(encoding="utf-8")
    assert "SmartScreen" in texte
    assert "SHA-256" in texte


def test_l_identifiant_de_l_installeur_ne_bouge_pas():
    """C'est `AppId` — et pas le nom — qui fait qu'une mise à jour REMPLACE l'installation au
    lieu d'en poser une seconde. Le changer casserait toutes les installations existantes."""
    texte = ISS.read_text(encoding="utf-8")
    assert "AppId={{ABB50651-2E51-5191-BFC3-5B72BE031AF6}" in texte


# --------------------------------------------------------------------------- #
#  Les trois vérifications du gel — L37.7
# --------------------------------------------------------------------------- #

def _ecrire(tmp_path: Path, nom: str, charge: dict) -> Path:
    chemin = tmp_path / nom
    chemin.write_text(json.dumps(charge, ensure_ascii=False), encoding="utf-8")
    return chemin


def _diagnostic_sain() -> dict:
    return {"gele": True, "racine_livree": "C:/x/_internal",
            "resume": {"total": 15, "bloquant": 3},
            "verdicts": [{"identifiant": i} for i in verifier_gel.ATTENDUS_MACHINE_NUE]}


def test_un_diagnostic_sain_passe(tmp_path):
    assert verifier_gel.verifier_diagnostic(
        _ecrire(tmp_path, "d.json", _diagnostic_sain())) == []


def test_un_binaire_qui_ne_se_sait_pas_gele_echoue(tmp_path):
    charge = _diagnostic_sain() | {"gele": False}
    echecs = verifier_gel.verifier_diagnostic(_ecrire(tmp_path, "d.json", charge))
    assert any("gel" in e for e in echecs), echecs


def test_un_diagnostic_vide_echoue(tmp_path):
    """⚠ **Le test qui compte.** Un gel dont les chemins sont faux ne rend pas des verdicts
    faux : il n'en rend aucun. Un garde-fou qui accepterait zéro verdict serait vert sur
    exactement le défaut qu'il existe pour attraper."""
    charge = {"gele": True, "racine_livree": "C:/x", "resume": {"total": 0}, "verdicts": []}
    echecs = verifier_gel.verifier_diagnostic(_ecrire(tmp_path, "d.json", charge))
    assert echecs


@pytest.mark.parametrize("manquant", verifier_gel.ATTENDUS_MACHINE_NUE)
def test_un_point_attendu_absent_echoue(tmp_path, manquant):
    charge = _diagnostic_sain()
    charge["verdicts"] = [v for v in charge["verdicts"] if v["identifiant"] != manquant]
    echecs = verifier_gel.verifier_diagnostic(_ecrire(tmp_path, "d.json", charge))
    assert any(manquant in e for e in echecs), echecs


def test_un_demarrage_sain_passe(tmp_path):
    charge = {"ok": True, "destination": "accueil", "echecs": []}
    assert verifier_gel.verifier_demarrage(_ecrire(tmp_path, "s.json", charge)) == []


def test_un_tome_ouvert_au_demarrage_echoue(tmp_path):
    """Critère 2 du `PLAN-31`, revérifié sur le gel."""
    charge = {"ok": False, "destination": "retouche",
              "echecs": ["un Tome est ouvert alors que personne ne l'a demandé"]}
    assert verifier_gel.verifier_demarrage(_ecrire(tmp_path, "s.json", charge))


def test_le_bruit_d_une_dependance_tierce_ne_casse_pas_la_lecture(tmp_path):
    """Mesuré le 2026-09-06 : `transformers` écrit un avertissement avant le premier octet.
    Le relevé se lit à la dernière ligne JSON, pas au fichier entier."""
    chemin = tmp_path / "s.json"
    chemin.write_text("[transformers] blah blah\n"
                      '{"ok": true, "destination": "accueil", "echecs": []}\n',
                      encoding="utf-8")
    assert verifier_gel.verifier_demarrage(chemin) == []


def test_les_empreintes_ne_listent_que_ce_qui_est_publie(tmp_path):
    (tmp_path / "Angelith-9.9.9-setup.exe").write_bytes(b"installeur")
    (tmp_path / "SHA256SUMS.txt").write_text("bruit", encoding="utf-8")
    (tmp_path / "Angelith").mkdir()
    (tmp_path / "Angelith" / "angelith-gui.exe").write_bytes(b"gel")
    lignes = verifier_gel.empreintes(tmp_path)
    assert [nom for _sha, nom in lignes] == ["Angelith-9.9.9-setup.exe"]
    assert len(lignes[0][0]) == 64


def test_l_outil_rend_un_code_d_erreur_sur_un_releve_fautif(tmp_path):
    """Bout en bout : si l'outil ne sortait pas en erreur, les trois étapes de CI seraient
    vertes quoi qu'il arrive."""
    mauvais = _ecrire(tmp_path, "d.json", {"gele": False, "resume": {}, "verdicts": []})
    code = subprocess.run([sys.executable, "tools/verifier_gel.py", "--diagnostic",
                           str(mauvais)], cwd=RACINE, capture_output=True).returncode
    assert code == 1


# --------------------------------------------------------------------------- #
#  Le job de CI existe, et il teste
# --------------------------------------------------------------------------- #

def test_la_ci_construit_et_verifie_l_artefact():
    ci = (RACINE / ".github/workflows/ci.yml").read_text(encoding="utf-8")
    assert "\n  artefact:" in ci
    # ⚠ **Le job n'énumère plus les étapes, il appelle l'outil** (lot 38). Ce qu'on vérifie ici
    # est donc le CÂBLAGE ; le contenu des étapes est vérifié sur `tools/geler.py`, qui a des
    # tests — alors qu'un `run:` de YAML n'en a jamais eu.
    for etape in ("python tools/geler.py --outils", "python tools/geler.py",
                  "SHA256SUMS.txt", "notes_de_version.py"):
        assert etape in ci, etape
    outil = (RACINE / "tools" / "geler.py").read_text(encoding="utf-8")
    for etape in ("--version", "--diagnostic-json", "--verifier-demarrage"):
        assert etape in outil, etape


def test_la_ci_ne_gele_pas_a_chaque_push():
    """Un gel de 390 Mo à chaque push paierait un artefact que personne ne télécharge."""
    ci = (RACINE / ".github/workflows/ci.yml").read_text(encoding="utf-8")
    bloc = ci[ci.index("\n  artefact:"):]
    assert "refs/tags/" in bloc.split("steps:")[0]


# --------------------------------------------------------------------------- #
#  `tools/geler.py` — compiler en UNE commande (lot 38)
# --------------------------------------------------------------------------- #

def test_l_outil_de_compilation_existe():
    assert (RACINE / "tools" / "geler.py").is_file()


def test_il_cherche_inno_setup_aux_deux_emplacements():
    r"""⚠ **Ce test défend une correction, pas une préférence.** `ci.yml` codait en dur
    `C:\Program Files (x86)\Inno Setup 6\ISCC.exe` ; une installation par
    `winget --scope user` — celle de la machine principale du projet — met le compilateur dans
    `%LOCALAPPDATA%\Programs`. Le job de CI aurait marché, la commande documentée non."""
    from tools import geler
    candidats = " ".join(geler.ISCC_CANDIDATS)
    assert "%LOCALAPPDATA%" in candidats
    assert "Program Files (x86)" in candidats


def test_il_n_ecrit_jamais_dans_le_dossier_des_oeuvres():
    """`build/` porte les SORTIES du pipeline — des tomes qui coûtent des heures de GPU."""
    from tools import geler
    assert geler.TRAVAIL != "build"
    assert geler.TRAVAIL.startswith(".")


def test_il_n_installe_rien():
    """Même ligne que `core/reparations.py` : Angelith n'installe aucun logiciel système, et
    un empaqueteur n'est pas une dépendance de ce qu'il empaquette. L'outil DIT la commande."""
    code = (RACINE / "tools" / "geler.py").read_text(encoding="utf-8")
    corps = _sans_docstrings_ni_commentaires(code)
    # ⚠ On cherche une EXÉCUTION, pas le mot. L'outil DIT « winget install … » et
    # « pip install pyinstaller » dans ses messages d'absence : c'est précisément ce qu'on
    # attend de lui — dire la commande et s'arrêter là, comme `core/reparations.py`.
    # ⚠ Sur des MOTS, pas des sous-chaînes : `capture_output=True` contient « apt ».
    import re
    gestionnaires = re.compile(r"(winget|choco|scoop|apt-get|apt|dnf|pacman|brew|pip)")
    executions = [ln for ln in corps.splitlines()
                  if ("subprocess" in ln or "os.system" in ln or "Popen" in ln)
                  and gestionnaires.search(ln)]
    assert not executions, executions


def _sans_docstrings_ni_commentaires(code: str) -> str:
    import ast
    arbre = ast.parse(code)
    for noeud in ast.walk(arbre):
        if isinstance(noeud, (ast.Module, ast.ClassDef, ast.FunctionDef,
                              ast.AsyncFunctionDef)) and ast.get_docstring(noeud):
            noeud.body = noeud.body[1:] or [ast.Pass()]
    return ast.unparse(arbre)


def test_pyinstaller_n_est_declare_dans_aucun_requirements():
    """⚠ Délibéré, et l'outil le dit dans son message d'absence : un empaqueteur n'est pas une
    dépendance de ce qu'il empaquette. Le jour où quelqu'un l'ajoute, ce test le lui rappelle."""
    import tomllib
    projet = tomllib.loads((RACINE / "pyproject.toml").read_text(encoding="utf-8"))
    tous = list(projet["project"]["dependencies"])
    for paquets in projet["project"]["optional-dependencies"].values():
        tous += list(paquets)
    assert not [p for p in tous if "pyinstaller" in p.lower()]


def test_l_outil_declare_les_trois_verifications():
    """Les trois pannes classiques du gel, chacune rencontrée pour de vrai au lot 37."""
    from tools import geler
    source = (RACINE / "tools" / "geler.py").read_text(encoding="utf-8")
    assert "--version" in source
    assert "--diagnostic-json" in source
    assert "--verifier-demarrage" in source
    assert callable(geler.verifier)


def test_les_verifications_tournent_sur_le_binaire_console():
    """Sous Windows, un binaire lié en sous-système « fenêtre » n'a pas de sortie standard :
    le premier essai de ces vérifications, au lot 37, n'a rien écrit et n'est jamais sorti."""
    corps = _sans_docstrings_ni_commentaires(
        (RACINE / "tools" / "geler.py").read_text(encoding="utf-8"))
    assert "angelith-console.exe" in corps
    # ⚠ Docstrings exclues : l'une d'elles EXPLIQUE pourquoi le binaire fenêtré ne convient
    # pas, et le mot doit pouvoir y figurer.
    assert "angelith-gui.exe" not in corps


def test_la_ci_appelle_l_outil_au_lieu_de_reecrire_la_sequence():
    """⚠ C'est ce qui rend le chemin local et le chemin d'intégration identiques. Deux
    séquences pour la même chose finissent par en faire deux — c'est exactement ce qui est
    arrivé au chemin d'Inno Setup."""
    ci = (RACINE / ".github/workflows/ci.yml").read_text(encoding="utf-8")
    bloc = ci[ci.index("\n  artefact:"):]
    assert "python tools/geler.py" in bloc
    assert "ISCC.exe" not in bloc, "la CI code encore un chemin Inno Setup en dur"
    assert "pyinstaller angelith.spec" not in bloc, "la CI réécrit encore la commande de gel"


def test_l_outil_verifie_la_version_avant_de_geler():
    """Découvrir un `installeur/version.iss` périmé après huit minutes de PyInstaller est
    exactement ce qui est arrivé au lot 37 : l'installeur mesuré portait 2.30.0."""
    source = (RACINE / "tools" / "geler.py").read_text(encoding="utf-8")
    rang_version = source.index("installeur/generer.py")
    rang_gel = source.index('"angelith.spec"')
    assert rang_version < rang_gel


# --------------------------------------------------------------------------- #
#  La release porte ses fichiers — le prérequis de la mise à jour (lot 40)
#
#  ⚠ Ces tests gardent un CÂBLAGE de YAML, qui n'a pas d'autre filet. Le manque qu'ils
#  ferment était nommé dans `publication.yml` lui-même : « la release qu'il crée ne porte
#  aucun fichier ». Un updater n'aurait eu rien à télécharger, et personne ne l'aurait su
#  avant d'avoir poussé un tag.
# --------------------------------------------------------------------------- #

def _job_artefact() -> str:
    ci = (RACINE / ".github/workflows/ci.yml").read_text(encoding="utf-8")
    return ci[ci.index("\n  artefact:"):]


def test_la_release_recoit_l_installeur_ET_ses_empreintes():
    """⚠ **Les deux, ou rien.** Sans `SHA256SUMS.txt`, `core/maj.py` refuse de télécharger
    l'installeur — un fichier qu'on ne peut pas vérifier vaut moins qu'un lien vers la page,
    parce qu'il aurait l'air vérifié."""
    bloc = _job_artefact()
    assert "action-gh-release" in bloc, "la release ne reçoit aucun fichier"
    accroche = bloc[bloc.index("action-gh-release"):]
    assert "dist/*.exe" in accroche
    assert "dist/SHA256SUMS.txt" in accroche


def test_l_attachement_ne_part_que_sur_un_tag():
    """Le job tourne aussi en `workflow_dispatch`, pour vérifier qu'un gel PASSERAIT. Attacher
    des fichiers dans ce mode écrirait sur une release au hasard."""
    bloc = _job_artefact()
    accroche = bloc[:bloc.index("action-gh-release")]
    assert "refs/tags/v" in accroche.rsplit("- name:", 1)[-1]


def test_le_job_a_le_droit_d_ecrire_sur_le_depot_et_rien_de_plus():
    """⚠ La portée minimale, comme `publication.yml`. Un jeton plus large sur un job qui
    exécute une action tierce serait une élévation gratuite."""
    bloc = _job_artefact()
    entete = bloc[:bloc.index("steps:")]
    assert "permissions:" in entete
    assert "contents: write" in entete
    for portee in ("packages:", "id-token:", "actions: write"):
        assert portee not in entete, portee


def test_l_action_tierce_est_epinglee_au_correctif():
    """Elle reçoit un jeton d'écriture : une étiquette flottante changerait ce qu'elle en fait
    sans qu'un commit l'indique. Même règle que le scanner Sonar."""
    import re
    bloc = _job_artefact()
    trouve = re.search(r"softprops/action-gh-release@v(\d+)\.(\d+)\.(\d+)", bloc)
    assert trouve, "l'action de release n'est pas épinglée à un correctif"


def test_les_deux_workflows_ecrivent_le_MEME_corps():
    """⚠ Les deux partent du même tag et écrivent sur la même release, dans un ordre non
    garanti. Le même générateur sur le même CHANGELOG rend le même texte à l'octet près : c'est
    ce qui rend l'ordre sans conséquence, par construction et non par pari sur ce qu'une action
    tierce fait d'une release dont on ne lui donne pas le corps."""
    bloc = _job_artefact()
    publication = (RACINE / ".github/workflows/publication.yml").read_text(encoding="utf-8")
    assert "notes_de_version.py" in bloc
    assert "notes_de_version.py" in publication
    assert "body_path: dist/notes.md" in bloc


def test_publication_ne_cherche_aucun_fichier_windows_sur_un_runner_linux():
    """`publication.yml` tourne sur `ubuntu-latest` et n'a jamais construit d'installeur. Un
    `files:` y ferait échouer la publication sur des fichiers qui n'ont jamais existé là."""
    brut = (RACINE / ".github/workflows/publication.yml").read_text(encoding="utf-8")
    # ⚠ Les COMMENTAIRES retirés d'abord : l'en-tête de ce fichier explique justement où les
    # fichiers sont attachés, et il les nomme. Chercher dans le texte entier ferait échouer le
    # test sur la prose qui documente la décision qu'il vérifie.
    directives = [l for l in brut.splitlines() if not l.lstrip().startswith("#")]
    directives = chr(10).join(directives)
    assert "dist/*.exe" not in directives
    # ⚠ La clé cherchée porte son indentation, et non la sous-chaîne « files: » toute nue :
    # `fail_on_unmatched_files:` la contient, et le test échouait sur son propre garde-fou.
    assert (chr(10) + "          files:") not in directives
