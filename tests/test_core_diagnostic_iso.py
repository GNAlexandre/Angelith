# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Alexandre Tournel

"""⚠ **La sortie console des deux doctors est un CONTRAT SCRIPTÉ.** Ce fichier la gèle.

## Pourquoi ce fichier existe

Le `PLAN-36` L36.1 pose une exigence avant toutes les autres : « la sortie console reste iso,
octet pour octet. `run_manga.py --check` et `run.py --check` sont scriptés ; un test capture
leur sortie avant et après le refactor et les compare. Le refactor consiste à **extraire** le
constat de l'impression, pas à réécrire le texte. »

Le lot 36 a déplacé ces deux doctors vers `core/diagnostic.py` : ils rendent maintenant des
`Verdict` structurés et écrivent par un `ecrire` passé en paramètre. Sans ce fichier, rien
n'empêcherait un futur lot de « améliorer » une phrase et de casser silencieusement le script
de quelqu'un.

## Ce que le gabarit couvre, et ce qu'il ne couvre PAS

Les gabarits ci-dessous sont les lignes **déterministes** des deux doctors, relevées sur le
dépôt en 2.29.0 le 2026-09-06, avant le refactor, par `python run.py --check` et
`python run_manga.py --check`.

⚠ **La section « — Ollama — » n'y est pas**, et c'est dit plutôt que caché : elle dépend d'un
serveur, de sa liste de modèles et d'une génération. La geler ici demanderait un serveur en
CI, ce que le critère 11 du plan interdit (« `pytest` passe **sans réseau** »). Ce que ce
fichier garantit est donc : *tout ce qui ne dépend pas du réseau est inchangé*. La section
Ollama, elle, n'a pas été touchée par le lot — `core.llm.test_connection` a gagné un paramètre
`ecrire` dont le défaut est `print`, et `tests/test_core_llm_ecrire.py` vérifie que les deux
chemins produisent les mêmes lignes.

⚠ **Les chemins et les listes de modèles ne sont pas gelés non plus** : ils dépendent de la
machine. Le gabarit porte donc la FORME de chaque ligne — son symbole, son libellé, sa
ponctuation — et les lignes qui portent un chemin sont comparées sur leur préfixe.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from core import diagnostic as diag

RACINE = Path(__file__).resolve().parent.parent


# --------------------------------------------------------------------------- #
#  Le gabarit — relevé le 2026-09-06 sur 2.29.0, AVANT le refactor
# --------------------------------------------------------------------------- #

#: Les lignes du doctor light novel, dans l'ordre, avec Pandoc et weasyprint présents et une
#: configuration complète. `…` marque une fin de ligne qui dépend de la machine.
GABARIT_LN: tuple[str, ...] = (
    "— Structure de config.yaml —",
    "✓ Toutes les sections principales sont présentes.",
    "\n— Chemins —",
    "✓ sources : …",
    "✓ style_guide : …",
    "\n— Outils externes —",
    "✓ Pandoc trouvé.",
)

#: Les lignes du doctor manga, même relevé, section `manga:` complète.
GABARIT_MANGA: tuple[str, ...] = (
    "— Section config.yaml > manga —",
    "✓ Toutes les clés principales sont présentes.",
    "\n— Dépendances Python additionnelles —",
)


def _compare(obtenues: list[str], gabarit: tuple[str, ...]) -> None:
    assert len(obtenues) >= len(gabarit), (
        f"le doctor a écrit {len(obtenues)} ligne(s) pour un gabarit de {len(gabarit)} :\n"
        + "\n".join(map(repr, obtenues)))
    for rang, (obtenue, attendue) in enumerate(zip(obtenues, gabarit)):
        if attendue.endswith("…"):
            prefixe = attendue[:-1]
            assert obtenue.startswith(prefixe), (
                f"ligne {rang} : attendu un début « {prefixe} », obtenu « {obtenue} »")
        else:
            assert obtenue == attendue, f"ligne {rang} : « {obtenue} » ≠ « {attendue} »"


@pytest.fixture()
def config_ln(tmp_path: Path) -> dict:
    (tmp_path / "sources").mkdir()
    (tmp_path / "style_guide.md").write_text("x", encoding="utf-8")
    return {
        "llm": {"base_url": "http://127.0.0.1:1/v1"}, "modeles": {"traducteur": "m"},
        "temperatures": {}, "decoupage": {}, "langues": {}, "garde_fous": {},
        "rendu": {"formats": [], "pdf_engine": "weasyprint"}, "options": {},
        "chemins": {"sources": str(tmp_path / "sources"),
                    "style_guide": str(tmp_path / "style_guide.md")},
    }


# --------------------------------------------------------------------------- #
#  L'isométrie
# --------------------------------------------------------------------------- #

def test_le_doctor_light_novel_ecrit_exactement_le_gabarit(config_ln, monkeypatch):
    """Critère 2 du `PLAN-36` : « identique octet pour octet avant/après »."""
    monkeypatch.setattr("shutil.which", lambda nom: "/usr/bin/" + nom)
    from pipeline import doctor

    lignes: list[str] = []
    doctor.sections(config_ln, ecrire=lignes.append, reseau=False)
    _compare(lignes, GABARIT_LN)


def test_le_doctor_manga_ecrit_exactement_le_gabarit(tmp_path):
    from manga import doctor as doctor_manga

    config = {"manga": {"modeles": {}, "temperatures": {},
                        "detection": {"model_path": str(tmp_path / "absent.onnx"),
                                      "telechargement_auto": False}}}
    lignes: list[str] = []
    doctor_manga.sections(config, ecrire=lignes.append, reseau=False, telechargement=True)
    _compare(lignes, GABARIT_MANGA)


def test_le_message_de_poids_absent_est_celui_d_avant(tmp_path):
    """⚠ Ces deux lignes précises sont citées dans `manga_models/README.md` et lues par des
    utilisateurs qui cherchent quoi faire. Les réécrire casserait la documentation avec."""
    from manga import doctor as doctor_manga

    absent = tmp_path / "absent.onnx"
    config = {"manga": {"modeles": {}, "temperatures": {},
                        "detection": {"model_path": str(absent),
                                      "telechargement_auto": False}}}
    lignes: list[str] = []
    doctor_manga.sections(config, ecrire=lignes.append, reseau=False, telechargement=True)
    assert (f"❌ modèle introuvable : {absent} — voir manga_models/README.md." in lignes)
    assert "  → manga.detection.telechargement_auto: true le récupérerait tout seul." in lignes


def test_la_section_manga_absente_dit_exactement_la_meme_phrase():
    from manga import doctor as doctor_manga

    lignes: list[str] = []
    doctor_manga.sections({}, ecrire=lignes.append, reseau=False, telechargement=False)
    assert lignes == ["— Section config.yaml > manga —",
                      "❌ Section « manga: » absente de config.yaml."]


# --------------------------------------------------------------------------- #
#  La structure reproduit la console
# --------------------------------------------------------------------------- #

def test_les_lignes_console_des_verdicts_reproduisent_la_sortie(config_ln, monkeypatch):
    """⚠ **L'invariant qui rend le refactor vérifiable.** Ce qui a été écrit et ce qui a été
    STRUCTURÉ doivent être la même chose : sinon la page Diagnostic montrerait autre chose que
    la console, et personne ne saurait laquelle des deux ment."""
    monkeypatch.setattr("shutil.which", lambda nom: "/usr/bin/" + nom)
    from pipeline import doctor

    ecrites: list[str] = []
    sections = doctor.sections(config_ln, ecrire=ecrites.append, reseau=False)
    reconstituees = diag.texte_console(sections)
    assert reconstituees == "".join(ligne + "\n" for ligne in ecrites)


def test_collecter_en_silence_puis_reimprimer_rend_le_meme_texte(config_ln, monkeypatch):
    """Le chemin de la page Diagnostic (« Sortie console… ») : elle reconstitue le texte
    depuis les verdicts, sans relancer les doctors ni un second appel réseau."""
    monkeypatch.setattr("shutil.which", lambda nom: "/usr/bin/" + nom)
    from pipeline import doctor

    ecrites: list[str] = []
    doctor.sections(config_ln, ecrire=ecrites.append, reseau=False)
    silencieuses = doctor.sections(config_ln, ecrire=None, reseau=False)
    assert diag.texte_console(silencieuses) == "".join(l + "\n" for l in ecrites)


def test_run_manga_expose_toujours_son_point_d_entree_historique():
    """⚠ `run_manga._run_doctor` est importé par `app.py` et cité dans la docstring de la CLI.
    Le corps a déménagé dans `manga/doctor.py` ; le NOM reste, sinon le déménagement serait
    une rupture d'interface déguisée en refactor."""
    import run_manga

    assert callable(run_manga._run_doctor)


def test_le_doctor_manga_ne_vit_plus_dans_la_cli():
    """La règle de couche : « le diagnostic appartient à la BRIQUE qu'il examine, pas à une
    CLI » (`app.py`). L'interface graphique importait `from run_manga import _run_doctor` ;
    elle importe maintenant `manga.doctor`."""
    source = (RACINE / "gui" / "fenetre.py").read_text(encoding="utf-8")
    assert "from run_manga import" not in source
