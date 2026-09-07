# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Alexandre Tournel

"""La frontière de la brique d'illustration — **la propriété, pas le raisonnement**.

Le `PLAN-24` étape 0.1 demande trois tests, et ce fichier les porte. Ils sont l'exact
équivalent, pour la nouvelle brique, de ce que `tests/test_manga_clean.py` fait pour
`clean.py` : ils transforment une phrase du README en propriété vérifiée.

1. `illustration/` n'importe aucun module de `manga/`, `pipeline/`, `scan/` ni `gui/` ;
2. aucune fonction de `illustration/` n'ouvre en écriture un chemin qui existe déjà hors de
   son dossier — le garde de `frontiere.py` est armé PENDANT le run, pas seulement ici ;
3. une génération complète via `MoteurFactice` sur un tome témoin laisse **tous** les fichiers
   préexistants inchangés, empreinte SHA-256 par fichier avant et après.

Le troisième est celui qui compte. Les deux premiers peuvent être contournés par un import
tardif ou par un `os.system` ; le troisième constate le résultat sur le disque.
"""
import hashlib
import json
from pathlib import Path

import pytest

from illustration import frontiere, orchestrateur
from illustration import requete as requete_mod
from illustration.moteur import MoteurFactice

RACINE = Path(__file__).resolve().parent.parent
BRIQUES_INTERDITES = ("manga", "pipeline", "scan", "gui")


# ─────────────────────  1. Le graphe d'imports de la brique  ─────────────────────

def _sources_illustration():
    return sorted((RACINE / "illustration").glob("*.py"))


def test_la_brique_a_bien_des_sources():
    """Un test qui parcourt une liste vide passe toujours. Celui-ci vérifie qu'il y a
    quelque chose à vérifier."""
    assert len(_sources_illustration()) >= 5


@pytest.mark.parametrize("source", _sources_illustration(), ids=lambda p: p.name)
def test_illustration_n_importe_que_core(source):
    """`illustration` → `core`, et rien d'autre. Si une fonction de `manga/` est nécessaire,
    elle remonte dans `core/` — c'est ce que le `PLAN-24` L24.1 impose, et c'est ce qui garde
    le graphe d'imports du dépôt sans cycle."""
    import ast

    arbre = ast.parse(source.read_text(encoding="utf-8"), filename=str(source))
    for noeud in ast.walk(arbre):
        if isinstance(noeud, ast.Import):
            noms = [alias.name for alias in noeud.names]
        elif isinstance(noeud, ast.ImportFrom):
            noms = [noeud.module or ""]
        else:
            continue
        for nom in noms:
            racine = nom.split(".")[0]
            assert racine not in BRIQUES_INTERDITES, (
                f"{source.name} importe « {nom} » — la brique d'illustration n'importe que "
                f"core/. Remonte la fonction dont tu as besoin dans core/ plutôt que de "
                f"créer une arête vers {racine}/.")


def test_importer_la_brique_ne_charge_aucune_autre_brique():
    """Un import PARESSEUX dans une fonction échapperait à l'analyse statique ci-dessus. On
    vérifie donc aussi le résultat : importer toute la brique dans un interpréteur neuf ne
    doit charger ni manga, ni pipeline, ni scan, ni gui."""
    import subprocess
    import sys

    code = ("import sys, importlib\n"
            "for m in ('illustration', 'illustration.frontiere', 'illustration.moteur',\n"
            "          'illustration.requete', 'illustration.marquage',\n"
            "          'illustration.poids', 'illustration.comfyui',\n"
            "          'illustration.rapport', 'illustration.orchestrateur'):\n"
            "    importlib.import_module(m)\n"
            "print([m for m in sys.modules if m.split('.')[0] in "
            f"{BRIQUES_INTERDITES!r}])\n")
    out = subprocess.run([sys.executable, "-c", code], cwd=RACINE, capture_output=True,
                         text=True, encoding="utf-8")
    assert out.returncode == 0, out.stderr
    assert out.stdout.strip() == "[]", out.stdout


# ─────────────────  2. Aucune écriture sur un chemin préexistant  ─────────────────

def _arbre_temoin(tmp_path: Path) -> tuple[dict, str, str]:
    """Un tome témoin PEUPLÉ : des sources, une bible, des illustrations dans `media/`, un
    `RAPPORT.md` et un `perf.log` déjà écrits, un `.checkpoints/` déjà rempli.

    Les deux derniers ne sont pas décoratifs : ce sont exactement les fichiers que le
    `PLAN-24` L24.6 demandait de modifier, et que la frontière interdit de toucher."""
    from PIL import Image

    projet, tome = "Projet Témoin", "Vol.1"
    sources = tmp_path / "sources" / projet
    build = tmp_path / "build" / projet / tome
    (sources).mkdir(parents=True)
    (build / "media").mkdir(parents=True)
    (build / ".checkpoints").mkdir(parents=True)

    for nom in ("illus_01.png", "illus_02.png"):
        Image.new("RGB", (32, 48), (200, 180, 160)).save(build / "media" / nom)
    (build / "RAPPORT.md").write_text("# Rapport du tome\n\nintact\n", encoding="utf-8")
    (build / "perf.log").write_text("2026-08-29 ligne d'origine\n", encoding="utf-8")
    (build / ".checkpoints" / "detection.json").write_text('{"v": 1}', encoding="utf-8")
    (sources / "chapters").mkdir()
    (sources / "chapters" / "ch01.md").write_text("Elle avait les cheveux blonds.\n",
                                                  encoding="utf-8")

    from core import bible as bible_mod
    entree = bible_mod.personnage("Tory Noelle")
    entree["apparence"]["cheveux"] = "blonds, longs"
    entree["apparence"]["yeux"] = "gris"
    entree["citations"] = [
        {"attribut": "cheveux", "source": "chapters/ch01.md", "texte": "cheveux blonds"},
        {"attribut": "yeux", "source": "media/illus_01.png", "texte": "yeux gris"}]
    entree["references"] = [{"fichier": "media/illus_01.png", "role": "identite",
                             "confiance": "humaine"}]
    bible_mod.save({"personnages": [entree], "style": {"mots": "aquarelle, trait fin"}},
                   bible_mod.chemin(sources))

    config = {"chemins": {"sources": str(tmp_path / "sources"), "build": str(tmp_path / "build")},
              "illustration": {"actif": True, "moteur": "factice",
                               "vram": {"decharger_llm": False}}}
    return config, projet, tome


def _empreintes(racine: Path) -> dict[str, str]:
    sortie = {}
    for chemin in sorted(racine.rglob("*")):
        if chemin.is_file():
            sortie[str(chemin.relative_to(racine))] = hashlib.sha256(
                chemin.read_bytes()).hexdigest()
    return sortie


def test_le_garde_refuse_une_ecriture_hors_de_son_dossier(tmp_path):
    """Le mécanisme lui-même, isolé. Il est armé PENDANT le run, pas seulement en test."""
    (tmp_path / "oeuvre").mkdir()
    planche = tmp_path / "oeuvre" / "planche.png"
    planche.write_bytes(b"pixels d'origine")
    with frontiere.perimetre(tmp_path / "sortie"):
        (tmp_path / "sortie" / "neuf.txt").write_text("ok", encoding="utf-8")
        with pytest.raises(frontiere.EcritureHorsPerimetre):
            planche.write_bytes(b"ecrase")
        with pytest.raises(frontiere.EcritureHorsPerimetre):
            open(planche, "wb").write(b"ecrase")
        with pytest.raises(frontiere.EcritureHorsPerimetre):
            planche.unlink()
    assert planche.read_bytes() == b"pixels d'origine"


def test_le_garde_couvre_aussi_Image_save(tmp_path):
    """Le `PLAN-24` nomme `Image.save` : Pillow écrit par `builtins.open`, donc il est déjà
    couvert — on le vérifie plutôt que de le supposer."""
    from PIL import Image

    (tmp_path / "oeuvre").mkdir()
    cible = tmp_path / "oeuvre" / "sortie.png"
    with frontiere.perimetre(tmp_path / "sortie"):
        with pytest.raises(frontiere.EcritureHorsPerimetre):
            Image.new("RGB", (4, 4)).save(cible)
    assert not cible.exists()


def test_le_perimetre_imbrique_restreint_et_n_elargit_pas(tmp_path):
    with frontiere.perimetre(tmp_path / "a"):
        with frontiere.perimetre(tmp_path / "a" / "b"):
            with pytest.raises(frontiere.EcritureHorsPerimetre):
                (tmp_path / "a" / "hors.txt").write_text("x", encoding="utf-8")
        with pytest.raises(frontiere.EcritureHorsPerimetre):
            (tmp_path / "c").mkdir()


def test_le_garde_est_inerte_hors_contexte(tmp_path):
    """Un fil qui n'a rien armé n'est pas contraint : le garde protège le run, il ne
    prétend pas régenter le processus. Sans ça, `pytest` lui-même ne pourrait plus écrire."""
    assert frontiere.racines_actives() is None
    (tmp_path / "libre.txt").write_text("ok", encoding="utf-8")


def test_aucune_phase_n_ouvre_en_ecriture_un_chemin_preexistant(tmp_path, monkeypatch):
    """Le test que le `PLAN-24` décrit : on intercepte les écritures sur un arbre témoin
    PEUPLÉ, et on échoue si un fichier préexistant est visé.

    L'interception est posée **au-dessus** du garde de production : elle relève les cibles
    au lieu de se contenter de refuser, pour que l'échec nomme le fichier."""
    config, projet, tome = _arbre_temoin(tmp_path)
    existants = {str(p.resolve()) for p in tmp_path.rglob("*") if p.is_file()}
    vises: list[str] = []

    original = Path.write_text
    original_bytes = Path.write_bytes
    original_open = open

    def _relever(chemin):
        resolu = str(Path(chemin).resolve())
        if resolu in existants:
            vises.append(resolu)

    def _write_text(self, *a, **k):
        _relever(self)
        return original(self, *a, **k)

    def _write_bytes(self, *a, **k):
        _relever(self)
        return original_bytes(self, *a, **k)

    def _open(fichier, mode="r", *a, **k):
        if set("wax+") & set(str(mode)):
            _relever(fichier)
        return original_open(fichier, mode, *a, **k)

    monkeypatch.setattr(Path, "write_text", _write_text)
    monkeypatch.setattr(Path, "write_bytes", _write_bytes)
    monkeypatch.setattr("builtins.open", _open)

    orchestrateur.phase_prompt(projet, config, tome=tome)
    _valider(orchestrateur.dossier(config, projet))
    orchestrateur.phase_image(projet, config, moteur=MoteurFactice())

    assert vises == [], (
        "la brique a ouvert en écriture des fichiers qui existaient déjà : "
        f"{sorted(set(vises))}")


# ─────────────  3. Un run complet ne change aucune empreinte préexistante  ─────────────

def _valider(dossier_illustrations: Path) -> None:
    """Franchit la porte humaine, comme un utilisateur le ferait à la main."""
    cible = requete_mod.chemin(dossier_illustrations)
    doc = requete_mod.load(cible)
    doc["valide"] = True
    doc["validation"]["par"] = "test"
    doc["validation"]["date"] = "2026-08-29"
    requete_mod.save(doc, cible)


def test_un_run_complet_laisse_toutes_les_empreintes_prealables_inchangees(tmp_path):
    """**Le** test du lot. Empreinte SHA-256 par fichier, avant et après, sur tout l'arbre.

    C'est l'exact équivalent de ce que `tests/test_manga_clean.py` fait pour `clean.py` :
    il ne raisonne pas sur ce que le code devrait faire, il constate ce que le disque a."""
    config, projet, tome = _arbre_temoin(tmp_path)
    avant = _empreintes(tmp_path)

    orchestrateur.phase_prompt(projet, config, tome=tome)
    dossier = orchestrateur.dossier(config, projet)
    _valider(dossier)
    recap = orchestrateur.phase_image(projet, config, moteur=MoteurFactice())

    apres = _empreintes(tmp_path)
    modifies = {c: (avant[c], apres[c]) for c in avant
                if c in apres and avant[c] != apres[c]}
    disparus = sorted(set(avant) - set(apres))
    assert not modifies, f"fichiers préexistants MODIFIÉS : {sorted(modifies)}"
    assert not disparus, f"fichiers préexistants SUPPRIMÉS : {disparus}"

    # Et tout ce qui est neuf est dans le dossier de la brique, nulle part ailleurs.
    neufs = sorted(set(apres) - set(avant))
    assert neufs, "le run n'a rien produit — le test ne prouverait rien"
    hors = [n for n in neufs if "illustrations" not in Path(n).parts]
    assert not hors, f"fichiers neufs hors du dossier de la brique : {hors}"
    assert recap["images"], "aucune image générée"


def test_le_rapport_du_tome_et_le_perf_log_ne_sont_pas_touches(tmp_path):
    """L24.6 demandait une section dans le `RAPPORT.md` du tome ; le critère 1 bis interdit
    d'écrire dans un fichier préexistant. C'est la frontière qui gagne, et ce test fige
    l'arbitrage pour qu'il ne se redécouvre pas."""
    config, projet, tome = _arbre_temoin(tmp_path)
    racine_tome = orchestrateur.dossier_tome(config, projet, tome)
    rapport_tome = (racine_tome / "RAPPORT.md").read_text(encoding="utf-8")
    perf_tome = (racine_tome / "perf.log").read_text(encoding="utf-8")

    orchestrateur.phase_prompt(projet, config, tome=tome)
    _valider(orchestrateur.dossier(config, projet))
    orchestrateur.phase_image(projet, config, moteur=MoteurFactice())

    assert (racine_tome / "RAPPORT.md").read_text(encoding="utf-8") == rapport_tome
    assert (racine_tome / "perf.log").read_text(encoding="utf-8") == perf_tome
    # La brique a bien produit les siens, dans son dossier.
    propre = orchestrateur.dossier(config, projet)
    assert (propre / "RAPPORT.md").is_file()
    assert (propre / "perf.log").is_file()


def test_la_brique_ne_touche_pas_aux_checkpoints(tmp_path):
    """Interdit n° 1 : une relance de tome coûte des heures de GPU. La brique n'ajoute rien à
    `manga/checkpoints.py:STAGES`, n'incrémente aucun `FORMAT_VERSION` et ne lit ni n'écrit
    sous `.checkpoints/`."""
    config, projet, tome = _arbre_temoin(tmp_path)
    checkpoints = orchestrateur.dossier_tome(config, projet, tome) / ".checkpoints"
    avant = _empreintes(checkpoints)

    orchestrateur.phase_prompt(projet, config, tome=tome)
    _valider(orchestrateur.dossier(config, projet))
    orchestrateur.phase_image(projet, config, moteur=MoteurFactice())

    assert _empreintes(checkpoints) == avant


def test_le_sidecar_ne_porte_ni_le_titre_de_l_oeuvre_ni_le_tome(tmp_path):
    """Le `.gitignore` refuse déjà d'exposer les titres comme noms de dossier ; une image qui
    les porterait dans ses métadonnées les exposerait le jour où elle est partagée."""
    config, projet, tome = _arbre_temoin(tmp_path)
    orchestrateur.phase_prompt(projet, config, tome=tome)
    dossier = orchestrateur.dossier(config, projet)
    _valider(dossier)
    recap = orchestrateur.phase_image(projet, config, moteur=MoteurFactice())

    for entree in recap["images"]:
        texte = Path(entree["manifeste"]).read_text(encoding="utf-8")
        assert projet not in texte, "le nom de l'œuvre est dans le manifeste"
        assert json.loads(texte)["oeuvre"].startswith("oeuvre-")
