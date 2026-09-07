# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Alexandre Tournel

"""Diagnostic de l'environnement manga (`run_manga.py --check`, l'interface, le `.exe`).

## Pourquoi il déménage ici au lot 36

Il vivait dans `run_manga.py`, sous le nom `_run_doctor`. C'était la même inversion de couche
que le lot 2.6 avait défaite du côté light novel : l'interface graphique importait
`from run_manga import _run_doctor`, donc **la fenêtre dépendait d'une CLI**. `app.py` l'écrit
depuis longtemps — « le diagnostic appartient à la BRIQUE qu'il examine (sections de config,
chemins, Pandoc, moteur PDF), pas à une CLI ». Le light novel avait `pipeline/doctor.py` ; le
manga n'avait rien.

`run_manga._run_doctor` reste, et appelle ceci : la CLI n'a pas changé d'un octet, et rien de
ce qui l'importait ne casse.

## Ce qu'il rend

Des `core.diagnostic.Section` de `Verdict`, et il écrit au fil de l'eau si on lui passe un
`ecrire` (cf. `core/diagnostic.py` pour le contrat). La console de `run_manga.py --check` est
donc identique octet pour octet — vérifié par `tests/test_core_diagnostic_iso.py`.

## ⚠ Le téléchargement du détecteur, et pourquoi il reste dans le chemin console

`--check` télécharge le détecteur quand `manga.detection.telechargement_auto` le permet, et
c'est un comportement de 2.9.0 : « le diagnostic TÉLÉCHARGE plutôt que de signaler — c'est
justement le moment où l'utilisateur prépare sa machine ». Le `PLAN-36` L36.2 pose la règle
inverse pour l'interface : **rien ne se télécharge sans un clic explicite**.

Les deux tiennent ensemble, et la ligne est celle du GESTE : taper `run_manga.py --check` EST
le clic explicite ; ouvrir une page ne l'est pas. D'où le paramètre `telechargement`, à `True`
pour la console (comportement inchangé) et à `False` partout ailleurs — la page Diagnostic
constate l'absence et propose un bouton, elle ne se sert pas.
"""
from __future__ import annotations

from pathlib import Path

from core import cli
from core import config as core_config
from core import diagnostic as diag

#: Ce que la brique manga demande à pip, et la commande qui l'installe. Recopié tel quel de
#: `run_manga._run_doctor` : le texte de la console en dépend.
DEPENDANCES = [("numpy", "numpy"), ("onnxruntime", "onnxruntime"),
               ("manga_ocr", "manga-ocr"), ("PIL", "pillow")]

INDICE_PIP = "`pip install -r requirements-manga.txt`"


def _section_config(config: dict, ecrire=print) -> diag.Section:
    entete = "— Section config.yaml > manga —"
    diag.dire(ecrire, entete)
    mcfg = config.get("manga")
    if not mcfg:
        return diag.Section(entete, (diag.Verdict(
            "config_manga", diag.MANGA, diag.BLOQUANT,
            constat="la section « manga: » est absente de config.yaml",
            consequence="la brique manga n'a rien à lire : ni modèles, ni seuils, ni chemins.",
            geste="rétablis la section manga de config.yaml (git checkout config.yaml).",
            lignes_console=diag.dire(
                ecrire, "❌ Section « manga: » absente de config.yaml.")),))
    required = ["modeles", "temperatures", "detection"]
    missing = [k for k in required if k not in mcfg]
    if missing:
        return diag.Section(entete, (diag.Verdict(
            "config_manga", diag.MANGA, diag.BLOQUANT,
            constat=f"clé(s) manquante(s) dans manga: {missing}",
            consequence="les étapes qui les lisent partiraient sur des valeurs par défaut "
                        "non prévues.",
            geste="rétablis ces clés dans config.yaml > manga.",
            lignes_console=diag.dire(ecrire,
                                     f"❌ Clé(s) manquante(s) dans manga: {missing}")),))
    return diag.Section(entete, (diag.Verdict(
        "config_manga", diag.MANGA, diag.CONFORME,
        constat="toutes les clés principales de manga: sont présentes",
        lignes_console=diag.dire(ecrire, "✓ Toutes les clés principales sont présentes.")),))


def _section_detecteur(mcfg: dict, ecrire=print, *, telechargement: bool = True) -> diag.Section:
    """Le poids ONNX de détection de bulles.

    ⚠ **Non redistribuable, et c'est écrit dans le geste.** Angelith ne l'héberge pas, ne le
    miroite pas, et le récupère depuis sa source primaire, avec la licence affichée avant.
    Cf. `core/reparations.py`.

    ⚠ **MISE À JOUR 2026-09-06, lot 38 : la phrase qui était ici était FAUSSE.** Elle disait
    « le détecteur en place est GPL-3.0 + Manga109-s ». Manga109-s concerne le détecteur de
    **texte sur le dessin** (`manga/models.py:TEXTE_*`), pas celui des bulles. La licence
    n'est plus écrite ici du tout : elle se lit dans `manga/models.py`, source unique."""
    from . import models

    entete = "\n— Modèle de détection de bulles —"
    diag.dire(ecrire, entete)
    model_path = Path(mcfg.get("detection", {}).get("model_path", ""))
    det_cfg = mcfg.get("detection", {})
    if model_path.exists():
        taille = model_path.stat().st_size // (1024 * 1024)
        return diag.Section(entete, (diag.Verdict(
            "poids_detection", diag.MANGA, diag.CONFORME,
            constat=f"poids de détection présents : {model_path} ({taille} Mo)",
            lignes_console=diag.dire(
                ecrire, f"✓ modèle trouvé : {model_path} ({taille} Mo)")),))

    geste = ("récupère le poids depuis sa source primaire — la page Diagnostic le fait d'un "
             "bouton, licence affichée avant, empreinte SHA-256 enregistrée après. "
             "⚠ Angelith n'héberge ni ne redistribue aucun poids.")
    if telechargement and det_cfg.get("telechargement_auto", True):
        # Le diagnostic TÉLÉCHARGE plutôt que de signaler : c'est justement le moment où
        # l'utilisateur prépare sa machine, pas au milieu d'un tome de 150 planches. ⚠ Ce
        # chemin est celui de la CONSOLE, et de la console seulement — cf. l'en-tête du
        # module.
        lignes: list[str] = []

        def _noter(msg: str) -> None:
            lignes.append(msg)
            if ecrire is not None:
                ecrire(msg)

        try:
            models.assurer_detecteur(
                model_path, url=det_cfg.get("model_url") or models.DETECTEUR_URL,
                dire=_noter)
        except SystemExit as err:
            lignes.append(f"❌ {err}")
            if ecrire is not None:
                ecrire(f"❌ {err}")
            return diag.Section(entete, (diag.Verdict(
                "poids_detection", diag.MANGA, diag.BLOQUANT,
                constat=f"poids de détection absents et non récupérés : {model_path}",
                consequence="aucune bulle ne sera détectée : la brique manga ne peut pas "
                            "démarrer.",
                geste=geste, reparable=True, reparation="poids_detection",
                lignes_console=tuple(lignes)),))
        return diag.Section(entete, (diag.Verdict(
            "poids_detection", diag.MANGA, diag.CONFORME,
            constat=f"poids de détection récupérés : {model_path}",
            lignes_console=tuple(lignes)),))

    if telechargement:
        lignes = diag.dire(
            ecrire,
            f"❌ modèle introuvable : {model_path or '(non défini)'} — voir manga_models/README.md.",
            "  → manga.detection.telechargement_auto: true le récupérerait tout seul.")
    else:
        lignes = ()
    return diag.Section(entete, (diag.Verdict(
        "poids_detection", diag.MANGA, diag.BLOQUANT,
        constat=f"poids de détection absents : {model_path or '(non défini)'}",
        consequence="aucune bulle ne sera détectée : la brique manga ne peut pas démarrer.",
        geste=geste, reparable=True, reparation="poids_detection",
        lignes_console=lignes),))


def _section_police(mcfg: dict, ecrire=print) -> diag.Section:
    """La police de lettrage — présence, couverture du français, largeur, nom PostScript.

    ⚠ « police trouvée » était vrai et inutile : `resolve_font` rend TOUJOURS un chemin, y
    compris quand `font_path` désigne un fichier absent — il retombe alors en silence sur la
    chaîne par défaut. Le diagnostic annonçait donc un succès pendant que le tome partait dans
    une autre police. On mesure ce qui compte : le fichier est-il là, et sait-il dessiner le
    français ?"""
    from .psd import nom_postscript
    from .typeset import couverture, message_couverture, resolve_font

    entete = "\n— Police de lettrage —"
    diag.dire(ecrire, entete)
    demandee = (mcfg.get("typeset") or {}).get("font_path") or None
    lignes: list[str] = []

    def _noter(*msgs: str) -> None:
        for msg in msgs:
            lignes.append(msg)
            if ecrire is not None:
                ecrire(msg)

    try:
        police = resolve_font(demandee)
        couvre = couverture(demandee)
        avertissements = message_couverture(couvre)
        # La largeur n'est pas un défaut, c'est une prévision : elle s'affiche même quand
        # tout va bien. Seule une couverture incomplète — ou un fichier absent — mérite le
        # signe d'alerte.
        complet = couvre.existe and not couvre.manquants_alphabet
        _noter(f"{'✓' if complet else '⚠'} police : {police}")
        if complet:
            _noter(f"  couverture française complète · "
                   f"{couvre.largeur_relative:.2f}× ComicNeue-Bold en largeur")
        for ligne in avertissements:
            _noter(f"  {ligne}")
        if "psd" in ((mcfg.get("rendu") or {}).get("formats") or []) \
                and str((mcfg.get("rendu") or {}).get("psd_texte", "rasterise")) == "type":
            # Les calques de type d'un PSD ne portent PAS la police : ils la nomment. Photoshop
            # substitue en silence celle qu'il ne trouve pas — le calque reste éditable, mais le
            # lettrage change sans explication.
            _noter(f"  → les calques de texte du PSD déclareront « {nom_postscript(police)} » : "
                   f"installe cette police côté système avant d'ouvrir les PSD dans Photoshop "
                   f"(cf. templates/fonts/README.md).")
    except SystemExit as err:
        # Même règle qu'au-dessus : `resolve_font` signale « aucune police » par
        # `SystemExit("message")`, et le diagnostic doit l'AFFICHER puis continuer — c'est
        # son rôle de tout inspecter avant de conclure. Un `SystemExit` porteur d'un code
        # n'est pas de cette famille et doit remonter.
        if not isinstance(err.code, str):
            raise
        _noter(f"❌ {err}")
        return diag.Section(entete, (diag.Verdict(
            "police_lettrage", diag.MANGA, diag.BLOQUANT,
            constat=f"aucune police de lettrage utilisable : {err}",
            consequence="le lettrage échouerait planche après planche.",
            geste="installe les polices libres du dépôt — `python tools/polices.py` (ou "
                  "`tools/installer_polices.ps1` sous Windows). Ce sont des polices sous "
                  "SIL OFL, récupérées avec consentement.",
            reparable=True, reparation="polices",
            lignes_console=tuple(lignes)),))

    if not couvre.existe and couvre.demandee:
        verdict = diag.Verdict(
            "police_lettrage", diag.MANGA, diag.BLOQUANT,
            constat=f"manga.typeset.font_path désigne un fichier absent : {couvre.demandee}",
            consequence=f"le tome sortirait en {police}, sans un mot de plus.",
            geste="corrige manga.typeset.font_path dans config.yaml, ou installe la police "
                  "manquante. Les polices libres du dépôt s'installent par "
                  "`python tools/polices.py`.",
            reparable=True, reparation="polices", lignes_console=tuple(lignes))
    elif couvre.manquants_alphabet:
        verdict = diag.Verdict(
            "police_lettrage", diag.MANGA, diag.DEGRADE,
            constat=f"la police {police.name} ne couvre pas tout l'alphabet français",
            consequence="les caractères manquants sortiraient en tofu (□) sur les planches.",
            geste="choisis une police à couverture complète — `python tools/polices.py` "
                  "installe celles que le dépôt a vérifiées.",
            reparable=True, reparation="polices", lignes_console=tuple(lignes))
    else:
        verdict = diag.Verdict(
            "police_lettrage", diag.MANGA, diag.CONFORME,
            constat=f"police de lettrage : {police} (couverture française complète)",
            lignes_console=tuple(lignes))
    return diag.Section(entete, (verdict,))


def sections(config: dict, *, ecrire=print, reseau: bool = True,
             telechargement: bool = True) -> tuple[diag.Section, ...]:
    """Le diagnostic manga, structuré, écrit au fil de l'eau si `ecrire`.

    `reseau=False` saute la section Ollama ; `telechargement=False` interdit toute
    récupération de poids (cf. l'en-tête du module). Les deux sont à `False` partout sauf
    dans la console.

    ⚠ Si la section `manga:` manque, on s'arrête là — comme avant. Continuer inspecterait des
    clés qui n'existent pas et produirait une cascade de faux constats."""
    blocs = [_section_config(config, ecrire)]
    mcfg = config.get("manga")
    if not mcfg:
        return tuple(blocs)
    # ⚠ Une clé manquante dans `manga:` ne stoppe PAS l'inspection, et c'est le comportement
    # d'avant : « le diagnostic doit tout inspecter avant de conclure, sinon l'utilisateur
    # relance la commande autant de fois qu'il a de problèmes ». Seule l'absence complète de
    # la section arrête, faute de quoi il y aurait des clés à lire.
    blocs.append(cli.section_dependances(DEPENDANCES, INDICE_PIP, ecrire=ecrire,
                                         brique=diag.MANGA))
    blocs.append(_section_detecteur(mcfg, ecrire, telechargement=telechargement))
    blocs.append(_section_police(mcfg, ecrire))
    if reseau:
        probe_config = dict(config, llm=core_config.section(config, "manga", "llm"),
                            modeles=mcfg.get("modeles", {}),
                            temperatures=mcfg.get("temperatures", {}))
        blocs.append(cli.section_ollama(probe_config, ecrire=ecrire))
    return tuple(blocs)


def run_doctor(config: dict) -> bool:
    """Diagnostic de l'environnement manga : section de config, dépendances Python
    additionnelles, modèle de détection, police de lettrage, connexion Ollama.

    ⚠ Le cas « section manga: absente » sort **sans ligne de conclusion**, comme avant : il
    n'y a rien à conclure sur une brique qui n'est pas configurée."""
    blocs = sections(config, ecrire=print)
    if not config.get("manga"):
        return False
    return cli.conclure(not diag.par_gravite(blocs, diag.BLOQUANT))
