# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Alexandre Tournel

"""L'**atelier console** : une commande, des questions, une image.

    python run_illustration.py "Mon LN"

## Ce que ce module est, et ce qu'il n'est pas

Il **pose des questions et affiche des réponses**. Toute décision est prise dans
`illustration/atelier.py`, qui est en Python nu et se teste sans console — c'est la règle de
couche du dépôt (`gui/__init__.py` : « toute logique métier vit dans le module […] ; ici on ne
trouve que des fenêtres, des scènes et des signaux »). Ce fichier-ci est l'équivalent console.

⚠ **Ce n'est pas l'atelier du `PLAN-27`.** Celui-là aura une galerie, un « garder / jeter » sur
les images produites et une insertion étiquetée dans le tome. Ici il n'y a qu'un chemin :
choisir qui, regarder ce qu'on va montrer au modèle, valider, générer.

## La porte humaine, en console

`requete.yaml` reste l'artefact — c'est lui qui part dans le sidecar, lui qui se relit six mois
plus tard, lui qui rend le rejeu possible. Ce que l'atelier change, c'est **où** l'humain le
lit : à l'écran, au moment où il demande l'image, plutôt que dans un éditeur de texte.

⚠ La question de validation n'a **pas de défaut à « oui »**, elle demande **un nom**, et ce nom
part dans `validation.par` puis dans le sidecar de chaque image. C'est la ligne exacte que la
politique IA du dossier de financement exige de pouvoir montrer, et un « [O/n] » ne la
montrerait pas.

## Pourquoi la revue des images a lieu ICI

`tools/bible.py --revue` valide des références **hors contexte** : on coche des images sans
savoir pour quelle illustration. L'atelier les montre au moment où l'on demande le portrait,
avec ce que le modèle de vision dit de chacune. C'est la même personne, le même œil, mieux
informé — et l'atelier propose ensuite d'inscrire ce choix dans la bible, par un geste
explicite (`atelier.promouvoir`), jamais par effet de bord.
"""
from __future__ import annotations

import sys
from pathlib import Path

from core import bible as bible_mod
from illustration import atelier as atelier_mod
from illustration import orchestrateur
from illustration import requete as requete_mod
from illustration import selection as selection_mod

#: Les cadrages proposés, avec ce qu'ils veulent dire à l'écran.
CADRAGES = (("visage", "gros plan sur le visage"),
            ("buste", "buste, à mi-corps — le défaut mesuré"),
            ("pied", "en pied, le personnage entier"))


def _console():
    from rich.console import Console
    return Console()


def atelier(args, config: dict) -> None:
    """Le chemin complet : choisir, regarder, valider, générer.

    ⚠ `Ctrl+C` et une entrée épuisée sortent **proprement**. Une trace de pile sur un
    abandon ferait passer une décision de l'utilisateur — « finalement, non » — pour une
    panne, et c'est exactement ce que `run_illustration.py:_attendues` évite déjà pour les
    garde-fous de la brique."""
    console = _console()
    try:
        _atelier(args, config, console)
    except (EOFError, KeyboardInterrupt):
        console.print("")
        console.print("[yellow]Abandonné.[/] Rien n'a été généré.")


def _atelier(args, config: dict, console) -> None:
    from rich.prompt import Confirm, IntPrompt, Prompt

    reg = orchestrateur.exiger_actif(config)
    projet = args.projet or _choisir_projet(config, console, Prompt)
    if not projet:
        return
    _bandeau(console, reg, projet, args.tome)
    if not _moteur_compatible(console, Confirm, reg):
        return

    bible_doc = bible_mod.load(bible_mod.chemin(orchestrateur.dossier_projet(config, projet)))
    if not (bible_doc.get("personnages") or []):
        console.print(
            f"[red]« {projet} » n'a pas de bible visuelle.[/] Sans elle, un prompt ne "
            f"viendrait pas de l'œuvre — il viendrait d'un modèle.\n"
            f"  → [cyan]python tools/bible.py \"{projet}\" --proposer[/] puis "
            f"[cyan]--revue[/]\n"
            f"  Tu peux quand même écrire une description toi-même : relance et choisis "
            f"« description personnalisée ».")
    glossaire = orchestrateur._glossaire(config, projet, lambda _m: None)
    racine = orchestrateur.racine_projet(config, projet)
    propositions = _propositions(config, projet)
    fiches = atelier_mod.catalogue(bible_doc, glossaire, racine, propositions=propositions)

    sujet = _choisir_sujet(console, Prompt, fiches)
    if sujet is None:
        return
    genre, valeur = sujet
    fiche = next((f for f in fiches if f.nom == valeur), None)

    cadrage = _choisir_cadrage(console, Prompt, reg)
    nombre = IntPrompt.ask("Combien d'images ?", default=1)

    if genre == "libre":
        doc = _requete_libre(config, projet, reg, valeur, cadrage=cadrage, nombre=nombre,
                             console=console, Confirm=Confirm, Prompt=Prompt,
                             bible_doc=bible_doc, racine=racine)
    else:
        doc = _requete_personnage(args, config, projet, reg, valeur, cadrage=cadrage,
                                  nombre=nombre, console=console, Confirm=Confirm,
                                  Prompt=Prompt, bible_doc=bible_doc, racine=racine,
                                  fiche=fiche)
    if doc is None:
        return

    if not _porte_humaine(console, Confirm, Prompt, args, doc, config, projet):
        console.print("[yellow]Rien n'a été généré.[/] `requete.yaml` est écrit et reste "
                      "modifiable à la main.")
        return
    _generer(console, config, projet, args)


# ───────────────────────────────  Choisir  ───────────────────────────────

def _propositions(config: dict, projet: str) -> dict:
    """`bible.propositions.yaml`, ou `{}`.

    ⚠ **Sans lui, une œuvre neuve n'aurait rien à proposer.** `tools/bible.py --proposer`
    écrit les propositions ; la revue humaine, elle, n'a pas encore eu lieu — et c'est
    justement ce que l'atelier vient faire."""
    import yaml

    chemin = bible_mod.chemin_propositions(orchestrateur.dossier_projet(config, projet))
    if not chemin.is_file():
        return {}
    return bible_mod.fill_defaults(yaml.safe_load(chemin.read_text(encoding="utf-8")) or {})


def _choisir_projet(config: dict, console, Prompt) -> str | None:
    """Les projets qui ont une bible, puis les autres. Un projet sans bible n'est pas exclu :
    on peut y écrire une description personnalisée."""
    racine = Path(config["chemins"]["sources"])
    projets = sorted(p.name for p in racine.iterdir() if p.is_dir()) if racine.is_dir() else []
    avec = [p for p in projets if bible_mod.chemin(racine / p).is_file()]
    sans = [p for p in projets if p not in avec]
    if not projets:
        console.print(f"[red]Aucun projet sous {racine}/[/]")
        return None
    console.print("\n[bold]Œuvres[/]")
    for i, nom in enumerate(avec + sans, 1):
        marque = "[green]bible[/]" if nom in avec else "[dim]sans bible[/]"
        console.print(f"  [cyan]{i}[/]. {nom}  {marque}")
    choix = Prompt.ask("Choix", choices=[str(i) for i in range(1, len(projets) + 1)],
                       default="1")
    return (avec + sans)[int(choix) - 1]


def _bandeau(console, reg: dict, projet: str, tome: str | None) -> None:
    """Ce qui est armé, avant la première question. Un utilisateur doit savoir qu'il va
    parler au moteur factice AVANT d'avoir répondu à six questions."""
    from rich.panel import Panel

    invite = reg["prompt"]
    lignes = [
        f"œuvre       : [bold]{projet}[/]"
        + (f"  (lecture restreinte à {tome})" if tome else "  (tous les tomes)"),
        f"moteur      : [bold]{reg['moteur']}[/]"
        + ("  [yellow]— un carré uni, aucun modèle : il vérifie la chaîne, pas l'image[/]"
           if reg["moteur"] == "factice" else ""),
        f"gabarit     : {invite['gabarit']} · {invite['langue']} · {invite['forme']}",
        "identité    : " + ("[green]armée[/]" if reg["identite"]["actif"] else
                             "[yellow]DÉSARMÉE — les références ne seront pas envoyées au "
                             "modèle (illustration.identite.actif)[/]"),
        "vision      : " + ("armée" if invite["llm"]["actif"] else
                             "désarmée (le choix d'images reste déterministe)"),
    ]
    console.print(Panel("\n".join(lignes), title="Atelier d'illustration", expand=False))


def _moteur_compatible(console, Confirm, reg: dict) -> bool:
    """Le moteur peut-il honorer ce que la configuration arme ? Sinon, on le dit **ici**.

    ⚠ **Le refus existait déjà, et il arrivait trop tard.** `moteur.verifier_canaux` bloque au
    moment de générer — après que l'utilisateur a choisi son personnage, relu ses images une
    par une, relu ses attributs et tapé son nom. Constaté à l'usage le 2026-08-31 sur une
    configuration qui armait l'identité avec le workflow texte-vers-image.

    Le message dit **quoi changer, avec le chemin exact** : « configurez le canal » n'aide
    personne. Et il n'interrompt pas d'autorité — une description personnalisée sans référence
    marche très bien sur ce workflow-là."""
    manquants = atelier_mod.canaux_manquants(reg, _canaux_du_moteur(reg))
    if not manquants:
        return True
    for canal in manquants:
        console.print(f"[red]⚠ Le canal « {canal} » est armé mais le moteur ne sait pas "
                      f"l'honorer.[/]")
        console.print("  " + atelier_mod.remede_canal(canal, reg["comfyui"]["workflow"]))
    console.print("[dim]Tu peux continuer : une description personnalisée SANS référence "
                  "passera. Un portrait de personnage, non — il sera refusé au moment de "
                  "générer.[/]")
    return Confirm.ask("Continuer quand même ?", default=False)


def _canaux_du_moteur(reg: dict):
    """Les canaux que le workflow armé déclare. `()` si on ne peut pas le savoir.

    ⚠ Aucun serveur n'est contacté : `MoteurComfyUI` lit les marqueurs dans le fichier du
    graphe à sa construction. Un bandeau qui demanderait un aller-retour réseau ne s'afficherait
    pas quand ComfyUI est éteint — c'est-à-dire au moment où on en a le plus besoin."""
    if reg["moteur"] != "comfyui" or not reg["comfyui"]["workflow"]:
        return ()
    try:
        from illustration.comfyui import MoteurComfyUI
        return MoteurComfyUI(reg["comfyui"]["workflow"]).CANAUX_SUPPORTES
    except Exception:                                    # noqa: BLE001 — diagnostic seulement
        return ()


def _choisir_sujet(console, Prompt, fiches) -> tuple | None:
    """`("personnage", nom)`, `("libre", description)` ou `None`."""
    illustrables = [f for f in fiches if f.illustrable]
    console.print("\n[bold]Qui veux-tu illustrer ?[/]")
    if not illustrables:
        console.print("  [yellow]Aucun personnage n'a à la fois un attribut cité et une "
                      "image candidate.[/] Ce n'est pas un échec de l'atelier : c'est ce que "
                      "la bible contient.")
    for i, f in enumerate(illustrables, 1):
        marque = ("[green]prêt[/]" if f.etat == atelier_mod.PRET
                  else "[yellow]à relire[/]")
        console.print(f"  [cyan]{i}[/]. {f.nom}  {marque}  [dim]{f.resume()}[/]")
    numero_libre = len(illustrables) + 1
    console.print(f"  [cyan]{numero_libre}[/]. [bold]Une description personnalisée[/] "
                  f"[dim]— je tape ce que je veux voir[/]")
    ecartes = [f for f in fiches if not f.illustrable]
    if ecartes:
        console.print(f"  [dim]{len(ecartes)} personnage(s) non proposé(s) : "
                      + ", ".join(f"{f.nom} ({atelier_mod.MOTIFS[f.motifs[0]]})"
                                  for f in ecartes[:4])
                      + (" …" if len(ecartes) > 4 else "") + "[/]")
    console.print("  [cyan]0[/]. Quitter")

    choix = Prompt.ask("Choix",
                       choices=[str(i) for i in range(0, numero_libre + 1)],
                       default="1" if illustrables else str(numero_libre))
    if choix == "0":
        return None
    if int(choix) == numero_libre:
        description = Prompt.ask("Décris l'image que tu veux (une ou deux phrases)")
        return ("libre", description) if description.strip() else None
    return ("personnage", illustrables[int(choix) - 1].nom)


def _choisir_cadrage(console, Prompt, reg: dict) -> str:
    console.print("\n[bold]Cadrage[/]  [dim]— il ne vient jamais du texte, c'est ton choix[/]")
    for i, (nom, quoi) in enumerate(CADRAGES, 1):
        console.print(f"  [cyan]{i}[/]. {nom} [dim]— {quoi}[/]")
    defaut = next((str(i) for i, (n, _) in enumerate(CADRAGES, 1)
                   if n == reg["prompt"]["cadrage"]), "2")
    choix = Prompt.ask("Choix", choices=[str(i) for i in range(1, len(CADRAGES) + 1)],
                       default=defaut)
    return CADRAGES[int(choix) - 1][0]


# ───────────────────────────  Regarder les images  ───────────────────────────

def _valider_les_images(args, config: dict, reg: dict, console, Confirm, nom: str,
                        candidates: list) -> tuple[list, dict]:
    """Montre chaque image candidate et laisse l'humain trancher. Rend `(retenues, avis)`.

    ⚠ **C'est ici que la revue humaine a lieu**, et c'est le cœur de l'atelier : on ne coche
    pas des références dans l'abstrait, on les regarde en sachant à quoi elles vont servir."""
    if not candidates:
        return [], {}
    avis: dict = {}
    if reg["prompt"]["llm"]["actif"] or Confirm.ask(
            f"\nFaire relire les {len(candidates)} image(s) par le modèle de vision ? "
            f"[dim](~5 s par image, il dit ce qu'il voit)[/]", default=True):
        avis = _avis_du_modele(config, reg, console, nom, candidates)

    plafond = reg["prompt"]["references_max"]
    console.print(f"\n[bold]Les images candidates de « {nom} »[/]  "
                  f"[dim]— le modèle en accepte {plafond} au plus (plafond mesuré au "
                  f"lot 25)[/]")
    retenues: list = []
    for candidate in _ordonner(candidates, avis):
        etiquettes = []
        if candidate.validee:
            etiquettes.append("[green]déjà validée[/]")
        if candidate.couverture:
            etiquettes.append("[red]COUVERTURE — titre et logo dans les pixels[/]")
        if candidate.classe:
            etiquettes.append(f"[dim]{candidate.classe}[/]")
        console.print(f"\n  {candidate.fichier}")
        console.print(f"    {' · '.join(etiquettes)}")
        if candidate.fichier in avis:
            console.print(f"    [dim]vision :[/] {avis[candidate.fichier]}")
        if len(retenues) >= plafond:
            console.print(f"    [dim]plafond de {plafond} atteint — non proposée[/]")
            continue
        conseil = _conseil(candidate, avis)
        if Confirm.ask("    la montrer au modèle ?", default=conseil):
            retenues.append(candidate.fichier)
    return retenues, avis


def _ordonner(candidates: list, avis: dict) -> list:
    """Les plus prometteuses d'abord : validées, puis non-couvertures, puis l'ordre de la
    bible. C'est l'ordre du lot 25, augmenté de ce que le modèle de vision a dit."""
    return sorted(candidates,
                  key=lambda c: (not c.validee, c.couverture,
                                 not _conseil(c, avis)))


def _conseil(candidate, avis: dict) -> bool:
    """Ce que l'atelier PROPOSE, jamais ce qu'il décide. Une couverture est déconseillée —
    elle porte le titre de l'œuvre en grandes lettres, et ces pixels partent au modèle."""
    if candidate.fichier in avis:
        return not avis[candidate.fichier].startswith("✗")
    return not candidate.couverture


def _avis_du_modele(config: dict, reg: dict, console, nom: str, candidates: list) -> dict:
    """`{fichier: avis}` — ce que le modèle de vision dit de chaque image.

    ⚠ Son verdict est **repris comme conseil, jamais comme décision**. Mesuré le 2026-08-30 :
    sur quatre motifs vérifiés à l'œil, quatre étaient exacts — et un cinquième refus était
    défendable sur les faits mais discutable sur la conclusion. C'est un bon conseiller, pas
    un juge."""
    invite = dict(reg["prompt"])
    invite["llm"] = {**invite["llm"], "actif": True}
    reg_llm = {**reg, "prompt": invite}
    systeme, modele = orchestrateur._prompt_de_selection(config, reg_llm, console.print)
    if not modele:
        return {}
    with console.status(f"Le modèle de vision regarde {len(candidates)} image(s)…"):
        choix, secondes, appels = selection_mod.choisir_avec_llm(
            candidates, plafond=len(candidates), usage=selection_mod.USAGE_IDENTITE,
            llm=orchestrateur._llm(config), modele=modele, systeme=systeme, personnage=nom,
            cote=invite["llm"]["cote_vision"], dire=lambda _m: None)
    console.print(f"[dim]{appels} appel(s), {secondes:.0f} s.[/]")
    return {c.fichier: ("" if c.retenue else "✗ ") + c.motif for c in choix}


# ───────────────────────────  Construire la requête  ───────────────────────────

def _requete_personnage(args, config: dict, projet: str, reg: dict, nom: str, *, cadrage: str,
                        nombre: int, console, Confirm, Prompt, bible_doc: dict, racine,
                        fiche=None):
    source = fiche.entree if fiche is not None else bible_mod.entree(bible_doc, nom)
    candidates = selection_mod.candidates_identite(
        {"personnages": [source]} if source else bible_doc, nom, racine)
    retenues, avis = _valider_les_images(args, config, reg, console, Confirm, nom, candidates)
    if not retenues:
        console.print(
            "[red]Aucune image retenue.[/] Sans référence, le modèle inventerait un visage au "
            "lieu de suivre celui de l'œuvre — la phase image refuse ce cas depuis le lot 25.")
        return None

    if not _revue(console, Confirm, config, projet, bible_doc, nom, retenues, candidates,
                  fiche):
        return None
    bible_doc = bible_mod.load(bible_mod.chemin(orchestrateur.dossier_projet(config, projet)))

    choix = selection_mod.Selection(
        references=atelier_mod.selection_humaine(retenues, candidates,
                                                 motifs_du_modele=avis))
    recap = orchestrateur.phase_prompt(
        projet, config, tome=args.tome, personnages=[nom], ecraser=True,
        cadrage=cadrage, forme=args.forme, langue=args.langue_prompt,
        graine=args.graine or None, selections={nom: choix},
        reporter=type("R", (), {"info": staticmethod(lambda m: None)})())
    doc = requete_mod.load(recap["requete"])
    for bloc in doc["images"]:
        bloc["nombre_images"] = max(1, int(nombre))
    return doc


def _requete_libre(config: dict, projet: str, reg: dict, description: str, *, cadrage: str,
                   nombre: int, console, Confirm, Prompt, bible_doc: dict, racine):
    """Une description écrite par l'humain, avec — s'il le veut — les références d'un
    personnage pour tenir l'identité."""
    references = []
    if Confirm.ask("Attacher les images de référence d'un personnage ?", default=False):
        noms = bible_mod.noms(bible_doc)
        for i, nom in enumerate(noms, 1):
            console.print(f"  [cyan]{i}[/]. {nom}")
        if noms:
            choix = Prompt.ask("Choix", choices=[str(i) for i in range(1, len(noms) + 1)],
                               default="1")
            nom = noms[int(choix) - 1]
            candidates = selection_mod.candidates_identite(bible_doc, nom, racine)
            retenues, avis = _valider_les_images(None, config, reg, console, Confirm, nom,
                                                 candidates)
            references = [c for c in atelier_mod.selection_humaine(
                retenues, candidates, motifs_du_modele=avis) if c.retenue]

    doc = requete_mod.vide(modele=orchestrateur._nom_modele(reg))
    doc.update({"forme": reg["prompt"]["forme"], "langue": reg["prompt"]["langue"],
                "gabarit": reg["prompt"]["gabarit"]})
    bloc = atelier_mod.bloc_libre(
        description, cadrage=cadrage, gabarit=reg["prompt"]["gabarit"],
        langue=reg["prompt"]["langue"], references=references, nombre_images=nombre)
    bloc.update({"largeur": reg["image"]["largeur"], "hauteur": reg["image"]["hauteur"],
                 "pas": reg["image"]["pas"], "guidage": reg["image"]["guidage"]})
    doc["images"] = [bloc]
    requete_mod.archiver_l_initial(doc)
    sortie = orchestrateur.dossier(config, projet)
    from illustration import frontiere
    with frontiere.perimetre(sortie):
        requete_mod.save(doc, requete_mod.chemin(sortie), projet=projet, tome="")
    return doc


def _revue(console, Confirm, config: dict, projet: str, bible_doc: dict, nom: str,
           retenues: list, candidates: list, fiche) -> bool:
    """La revue humaine, au moment où elle sert. Rend `False` si l'utilisateur refuse.

    ⚠ **Deux cas, et ils ne demandent pas la même chose.**

    - Le personnage est **déjà dans la bible** : ses attributs ont été relus ailleurs, on ne
      les remontre pas. On propose seulement d'inscrire les images qu'on vient de retenir.
    - Le personnage vient des **propositions** : rien n'a été relu — ni ses attributs, ni ses
      images. On montre alors les attributs AVEC LEURS CITATIONS, parce que c'est la règle du
      dépôt (« un attribut sans sa source n'est pas une observation »), et on ne l'écrit dans
      la bible que si l'humain le dit. Sans cette étape, `prompt.construire` ne trouverait même
      pas le personnage.

    ⚠ Dans les deux cas, une bible modifiée sans qu'on l'ait demandé serait une revue humaine
    fabriquée. La question est donc explicite, et elle ne se pose que s'il y a réellement
    quelque chose à écrire."""
    chemin = bible_mod.chemin(orchestrateur.dossier_projet(config, projet))
    depuis_propositions = fiche is not None and fiche.source == "propositions"

    retenue = None
    if depuis_propositions:
        retenue = _relire_les_attributs(console, Confirm, nom, fiche.entree)
        if retenue is None:
            console.print("[yellow]Aucun attribut retenu — rien n'est écrit.[/] Un portrait "
                          "sans attribut serait une invention présentée comme une "
                          "illustration de l'œuvre.")
            return False

    deja = {c.fichier for c in candidates if c.validee}
    neuves = [f for f in retenues if f not in deja]
    if not neuves and not depuis_propositions:
        return True
    if neuves:
        console.print(f"\n[dim]{len(neuves)} image(s) que tu viens de retenir ne sont pas "
                      f"encore marquées « validée par un humain ».[/]")
    if not Confirm.ask(f"Écrire ce choix dans {chemin.name} ?", default=True):
        # ⚠ Refuser est légitime pour un personnage DÉJÀ dans la bible — on génère quand même.
        # Ça ne l'est pas pour une proposition : sans écriture, il n'y a pas de personnage à
        # illustrer, et le dire vaut mieux que d'échouer trois écrans plus loin.
        if depuis_propositions:
            console.print("[yellow]Sans écriture, ce personnage n'existe pas pour la phase "
                          "image.[/] Rien n'a été généré.")
            return False
        return True
    modifiee, promues = atelier_mod.promouvoir(bible_doc, nom, neuves, entree=retenue)
    retires = bible_mod.save(modifiee, chemin)
    console.print(f"[green]{promues} référence(s) validée(s)[/] dans {chemin}")
    if retires:
        console.print(f"  [dim]⚠ {len(retires)} attribut(s) purgé(s) faute de citation : "
                      f"{retires}[/]")
    return True


def _relire_les_attributs(console, Confirm, nom: str, entree: dict):
    """La revue **attribut par attribut**, chacun avec sa phrase. Rend l'entrée filtrée, ou
    `None` si rien n'est retenu.

    ⚠ **En bloc, ce serait trop grossier, et la mesure l'a montré.** Sur le premier
    personnage relu de `roman N`, la passe automatique proposait cinq attributs dont trois
    faux : des cheveux « bleu céleste » là où le dessin les montre verts — la phrase citée
    décrit un AUTRE personnage —, un âge « environ deux ans » pour une adolescente, et un
    « masque blanc » tiré d'une phrase qui décrit les passants de la rue. Un « o/n » global
    n'aurait laissé que deux issues : écrire trois erreurs, ou perdre les deux bons attributs.

    ⚠ **Les citations sont montrées, pas résumées.** C'est ce qui permet de voir qu'une phrase
    parle de quelqu'un d'autre — et c'est exactement l'erreur la plus fréquente de la passe
    automatique."""
    console.print(f"\n[bold]« {nom} » n'est pas encore dans la bible visuelle.[/]  "
                  f"[dim]Voici ce que la passe automatique propose. Regarde la PHRASE : "
                  f"l'erreur la plus fréquente est un attribut pris à un autre personnage.[/]")
    gardes = []
    for attribut, valeur, citations in atelier_mod.attributs_cites(entree):
        console.print(f"\n  [cyan]{attribut}[/] : [bold]{valeur}[/]")
        for citation in citations[:3]:
            console.print(f"    [dim]↳ {citation.get('source', '?')} — "
                          f"« {str(citation.get('texte', ''))[:120]} »[/]")
        if Confirm.ask("    retenir ?", default=True):
            gardes.append(attribut)
    if not gardes:
        return None
    console.print(f"[dim]{len(gardes)} attribut(s) retenu(s). Un attribut sans citation ne "
                  f"sera pas écrit : la bible le purge à l'écriture.[/]")
    return atelier_mod.entree_filtree(entree, gardes)


# ───────────────────────────  La porte, puis la génération  ───────────────────────────

def _porte_humaine(console, Confirm, Prompt, args, doc: dict, config: dict,
                   projet: str) -> bool:
    """Montre ce qui va partir au modèle, demande un NOM, et n'a pas de défaut à « oui ».

    ⚠ **Depuis le lot 27, la console et l'interface graphique franchissent la MÊME porte** :
    `illustration/relecture.py:Porte`. Ce n'était pas le cas avant — cette fonction écrivait
    `valide: true` elle-même —, et deux portes, c'est une porte de moins qu'on croit avoir.
    Ce module ne fait plus qu'afficher ce que `relecture.ecrans` a construit, et transmettre
    le nom saisi.

    ⚠ L'écran montre maintenant **la source de chaque attribut** et **les anomalies avant le
    clic**, pas après : un attribut sans citation, une référence introuvable ou ambiguë, un
    terme négatif sans motif dans le gabarit. C'est le point 4 de L27.1 bis, et c'est le
    critère 2 du plan — « aucun message d'erreur n'apparaît APRÈS le clic »."""
    from rich.panel import Panel

    from illustration import relecture as relecture_mod

    porte = relecture_mod.Porte(
        doc, racine_projet=orchestrateur.racine_projet(config, projet))
    for ecran in porte.ecrans:
        console.print(Panel(_corps_de_relecture(ecran), title=ecran.nom, expand=False))
    for anomalie in porte.anomalies():
        console.print(f"[yellow]⚠ {anomalie}[/]")

    console.print("[dim]Le fichier complet est éditable : "
                  f"{requete_mod.chemin(orchestrateur.dossier(config, projet))}[/]")
    if not Confirm.ask("\n[bold]Valider ce prompt et générer ?[/]", default=False):
        return False
    par = args.par or Prompt.ask(
        "Ton nom [dim](il part dans le sidecar de chaque image — c'est ce qui distingue "
        "« assisté » de « généré »)[/]", default=_nom_par_defaut())
    try:
        valide = porte.valider(par=par)
    except (relecture_mod.PorteFermee, requete_mod.RequeteNonValidee) as err:
        console.print(f"[red]{err}[/]")
        return False
    sortie = orchestrateur.dossier(config, projet)
    from illustration import frontiere
    with frontiere.perimetre(sortie):
        requete_mod.save(valide, requete_mod.chemin(sortie), projet=projet, tome="")
    # Le laissez-passer est demandé ICI, et il lève si la porte n'a pas été franchie. Même
    # mécanique que l'onglet graphique : un seul objet, deux interfaces.
    porte.laissez_passer()
    return True


def _corps_de_relecture(ecran) -> str:
    """Ce qu'un écran de relecture donne à lire, en console. **Six choses, dans l'ordre.**"""
    from illustration import relecture as relecture_mod

    corps = [f"[bold]prompt[/]\n{ecran.prompt}"]
    if ecran.corrige:
        corps.append(f"\n[dim]prompt d'origine (phase 1) : {ecran.prompt_initial}[/]")
    corps.append(f"\n[bold]prompt négatif[/]\n[dim]{ecran.prompt_negatif}[/]")
    for terme in ecran.termes_negatifs:
        if not terme.explique:
            corps.append(f"  [yellow]« {terme.texte} » n'a pas de motif dans le gabarit[/]")
    for groupe, vignettes in ((relecture_mod.GROUPE_IDENTITE, ecran.references),
                              (relecture_mod.GROUPE_STYLE, ecran.ancrages)):
        retenues = [v for v in vignettes if v.retenue]
        if not retenues:
            continue
        corps.append(f"\n[bold]{relecture_mod.TITRES_GROUPE[groupe]}[/]")
        corps.append(f"[dim]{relecture_mod.AIDES_GROUPE[groupe]}[/]")
        for vignette in retenues:
            corps.append(f"  · {vignette.fichier}  [dim]{vignette.motif}[/]")
    if ecran.attributs:
        corps.append("\n[bold]d'où vient chaque mot[/]")
        for attribut in ecran.attributs:
            marque = "[yellow]⚠[/]" if attribut.anomalie else " "
            corps.append(f"{marque} · {attribut.attribut} = {attribut.valeur}  "
                         f"[dim]← {attribut.source or 'AUCUNE SOURCE'} "
                         f"({attribut.origine})[/]")
    armes = [c for c in ecran.canaux if c.arme]
    if armes:
        corps.append("\n[bold]canaux structurés[/]  [dim]— se désarment dans requete.yaml, "
                     "ne s'éditent pas ici[/]")
        for canal in armes:
            corps.append(f"  · {canal.nom} — {canal.description}")
    corps.append(f"\n[dim]{ecran.nombre_images} image(s), graine "
                 f"{ecran.graine if ecran.graine is not None else 'aléatoire'}[/]")
    return "\n".join(corps)


def _nom_par_defaut() -> str:
    """Le nom git de la machine, ou rien. Une valeur proposée n'est pas une valeur imposée."""
    import subprocess
    try:
        sortie = subprocess.run(["git", "config", "user.name"], capture_output=True,
                                text=True, timeout=5)
        return sortie.stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return ""


def _generer(console, config: dict, projet: str, args) -> None:
    from illustration.comfyui import ComfyIndisponible
    from illustration.identite import SansReferenceValidee
    from illustration.moteur import CanalRefuse

    try:
        with console.status("Génération…"):
            recap = orchestrateur.phase_image(projet, config, tome=args.tome,
                                              chemin_config=args.config,
                                              reporter=_reporter(console))
    except (ComfyIndisponible, CanalRefuse, SansReferenceValidee, ValueError) as err:
        console.print(f"[red]{err}[/]")
        return
    images = recap.get("images") or []
    console.print(f"\n[green]{len(images)} image(s)[/] dans {recap['dossier']}")
    for entree in images:
        console.print(f"  · {Path(entree['image']).name}  "
                      f"[dim]{entree['secondes']:.0f} s, graine {entree['graine']}[/]")
    console.print(f"Rapport : {Path(recap['dossier']) / 'RAPPORT.md'}")
    console.print("[dim]⚠ Ces images ne font pas partie de l'œuvre. Chacune porte son "
                  "marquage et son manifeste de provenance.[/]")


def _reporter(console):
    return type("R", (), {"info": staticmethod(
        lambda message: console.print(f"[dim]{message}[/]"))})()


def main() -> int:
    """Point d'entrée de secours, pour lancer l'atelier sans passer par la CLI."""
    sys.exit("Passe par run_illustration.py — c'est la façade de cette brique.")
