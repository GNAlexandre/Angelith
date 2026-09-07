# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Alexandre Tournel

"""Le croisement drapeau × interface — **critère 1 du `PLAN-33`**.

« Un inventaire à la main ne suffit pas, il faut le test » (`PLAN-19`, critère 1, écrit après
qu'un relevé de couleurs littérales en avait manqué trois sur vingt et une). Ces tests sont
ce test-là, appliqué aux quatre CLI.

Ils tournent **sans Qt et sans modèle** : `tools/inventaire_drapeaux.py` lit les sources avec
`ast` et `gui/parametres.py` n'importe pas PySide6.
"""
from tools import inventaire_drapeaux as inv


def test_chaque_drapeau_est_classe():
    """⚠ **C'est le test qui casse quand un drapeau neuf apparaît dans une CLI.**

    Il n'exige pas qu'un drapeau soit exposé — il exige qu'on ait tranché : formulaire
    déclaré, exposé ailleurs (bouton, menu, sélecteur de cible), ou non exposé **avec son
    motif**. Un « non » documenté est une réponse conforme ; le silence n'en est pas une."""
    orphelins = [(v.drapeau.cli, v.drapeau.nom)
                 for v in inv.croiser() if v.categorie == inv.ORPHELIN]
    assert orphelins == [], (
        "ces arguments ne sont ni exposés ni classés — ajoute-les à gui/parametres.py, "
        f"dans CATALOGUE, AILLEURS ou NON_EXPOSES avec un motif : {orphelins}")


def test_aucun_motif_ne_survit_a_son_drapeau():
    """Le pendant du précédent, et il compte autant.

    Un motif qui justifie un drapeau supprimé est un faux avertissement : il vieillit sans le
    dire, et il cesse d'être lu (règle §5 bis du contexte agent)."""
    morts = inv.declarations_orphelines()
    assert morts == (), (
        f"ces entrées de AILLEURS / NON_EXPOSES ne correspondent à aucun argument réel : "
        f"{morts}")


def test_tout_motif_de_non_exposition_dit_quelque_chose():
    """Un motif vide est un drapeau qu'on a fait taire, pas un drapeau qu'on a classé."""
    from gui import parametres as par

    courts = {cle: motif for cle, motif in par.NON_EXPOSES.items() if len(motif) < 40}
    assert courts == {}, f"motifs trop courts pour être des motifs : {courts}"
    vides = {cle: ou for cle, ou in par.AILLEURS.items() if len(ou) < 10}
    assert vides == {}, f"« exposé ailleurs » sans dire où : {vides}"


def test_les_trois_drapeaux_de_veille_sont_vus_a_travers_leur_helper():
    """⚠ Le §1.1 du `PLAN-33` comptait **23** `add_argument` dans `run_manga.py`. Il y en a
    **28**, et l'écart se décompose en deux erreurs de relevé distinctes :

    · **+2 parce que le plan est daté.** Il a été écrit sur la 2.24.1 ; le lot 31 (2.25.0) a
      ajouté `--fenetre-hauteur` et `--fenetre-recouvrement`, précisément pour que la
      destination Webtoon puisse les offrir. Le fichier en porte donc 25 ;
    · **+3 parce qu'ils ne sont pas écrits dans le fichier.** `cli.ajouter_flags_veille` pose
      `--keep-awake`, `--shutdown` et `--shutdown-delay` depuis `core/cli.py`, et aucun
      `grep add_argument run_manga.py` ne les verra jamais.

    C'est exactement l'écart que ce script existe pour supprimer — et il est du même ordre
    que celui qui a motivé le critère 1 du `PLAN-19`."""
    manga = [d for d in inv.drapeaux() if d.cli == "run_manga.py"]
    noms = [d.nom for d in manga]
    assert {"--keep-awake", "--shutdown", "--shutdown-delay"} <= set(noms)
    veille = [d for d in manga if d.nom == "--shutdown"]
    assert veille and veille[0].via == "core/cli.py:ajouter_flags_veille"
    ecrits = [d for d in manga if not d.via]
    assert len(ecrits) == 25, f"25 add_argument attendus dans le fichier, vu {len(ecrits)}"
    # ⚠ **29 depuis le lot 39, et le +1 est venu par un HELPER** : `cli.ajouter_flag_sans_llm`
    # pose `--sans-llm` depuis `core/cli.py`, exactement comme les trois de veille. Le compte
    # écrit dans le fichier, lui, ne bouge pas — c'est la démonstration que ce script sert à
    # quelque chose : un relevé manuel aurait vu 25 et manqué le quatrième.
    assert len(manga) == 29, f"29 arguments attendus au total, vu {len(manga)}"
    sans_llm = [d for d in manga if d.nom == "--sans-llm"]
    assert sans_llm and sans_llm[0].via == "core/cli.py:ajouter_flag_sans_llm"


def test_run_illustration_n_a_aucun_drapeau_de_veille():
    """⚠ Et c'est pour ça que l'atelier n'offre pas de run de nuit.

    `run_illustration.py` n'appelle pas `cli.ajouter_flags_veille`. Offrir « Éteindre le PC »
    dans l'atelier créerait un levier sans équivalent en ligne de commande — ce que
    `gui/__init__.py` interdit. Le test le PROUVE au lieu de le supposer."""
    from gui import parametres as par

    noms = {d.nom for d in inv.drapeaux() if d.cli == "run_illustration.py"}
    assert not (noms & {"--keep-awake", "--shutdown", "--shutdown-delay"})
    for identifiant in ("keep_awake", "shutdown", "shutdown_delay"):
        assert par.par_identifiant(par.ILLUSTRATIONS, identifiant) is None


def test_le_tableau_se_rend_en_markdown():
    """Le script est livré AVEC son résultat : `docs/mesures/lanceurs-2026-09-05.md` §2 le
    recopie, et cette ligne garantit qu'il reste reproductible."""
    tableau = inv.markdown()
    assert "| CLI | Argument | Verdict | Où / motif |" in tableau
    compte = inv.resume()
    assert compte["total"] == sum(compte[c] for c in (inv.FORMULAIRE, inv.AILLEURS,
                                                      inv.NON_EXPOSE, inv.ORPHELIN))
    assert compte["total"] > 90, "les quatre CLI portent plus de 90 arguments"


def test_aucun_helper_de_drapeaux_n_est_ignore_en_silence():
    """⚠ La contrepartie de l'AST est nommée dans le module : un drapeau posé par un helper
    inconnu serait invisible. Ce test refuse qu'un second helper naisse sans être déclaré."""
    import ast
    import pathlib

    suspects = []
    for cli in inv.CLIS:
        arbre = ast.parse((inv.RACINE / cli).read_text(encoding="utf-8"))
        for noeud in ast.walk(arbre):
            if not isinstance(noeud, ast.Call):
                continue
            cible = noeud.func
            nom = cible.attr if isinstance(cible, ast.Attribute) else getattr(cible, "id", "")
            if nom in inv.HELPERS or nom == "add_argument":
                continue
            if "flag" in nom or ("argument" in nom and nom != "add_argument"):
                suspects.append((cli, nom))
    assert suspects == [], (
        f"ces appels ressemblent à des poseurs de drapeaux non déclarés dans "
        f"tools/inventaire_drapeaux.HELPERS : {suspects}")
    assert pathlib.Path(inv.RACINE / "core" / "cli.py").is_file()
