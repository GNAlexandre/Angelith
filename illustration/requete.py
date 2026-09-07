# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Alexandre Tournel

"""`requete.yaml` — le format d'échange entre les deux phases **et l'humain**.

## Pourquoi un YAML commenté et pas le JSON qui part au moteur

Les deux existent, et ils ne servent pas à la même chose :

- **ce fichier** est ce qu'un humain relit et corrige. Il est en YAML parce que le dépôt vit
  de fichiers commentés — `config.yaml` est « un document » de 95 Ko de prose justifiée,
  `glossaire.yaml` porte ses bannières et tous ses champs même vides. **JSON ne sait pas
  porter un commentaire**, et la porte humaine dépend entièrement de la lisibilité du fichier ;
- **le payload** (`moteur.Requete.payload`) est le JSON typé dérivé de ce fichier au moment de
  l'appel, archivé tel quel dans le sidecar de provenance. C'est lui qui rend le rejeu exact
  possible.

⚠ **Deux formats, deux publics, UN SEUL contenu**, et c'est testé :
`tests/test_illustration_prompt.py` vérifie que le YAML relu et le payload archivé décrivent
la même requête (`PLAN-26` critère 1 septies). Sans ce test, la divergence des deux serait
invisible jusqu'au premier rejeu raté, c'est-à-dire trop tard.

## La porte, et elle est la seule chose qui compte ici

`valide: false` est le défaut, et **la phase image refuse de démarrer tant qu'il n'est pas
passé à `true`**. Un défaut à `true` annulerait le garde-fou ; une clé de configuration qui
l'assouplirait aussi, et il n'y en a pas. C'est ce qui garantit qu'aucun PNG n'existe sans
qu'un humain ait validé le prompt qui l'a produit.

⚠ **Depuis le lot 26, la porte a un SECOND battant** : `exiger_references_retenues`. Un
utilisateur peut vider `graine` et `attributs_sources` sans rien casser — ce sont des
commodités —, mais il ne peut pas décocher **toutes** les références d'un personnage qui en
avait : la phase 2 retomberait alors sur de la génération pure, ce que le `PLAN-25` L25.2
refuse déjà avec un motif nommé. Le refus est dit ici aussi, **à la lecture du fichier**,
avant la bascule VRAM et avant la première seconde de GPU.

⚠ Ce n'est PAS un `.checkpoints/` et il ne faut pas le confondre avec un. Le fichier vit
sous `build/<Projet>/<Tome>/illustrations/`, il n'entre pas dans `manga/checkpoints.py:STAGES`,
il n'incrémente aucun `FORMAT_VERSION`, et son absence ou son incohérence ne déclenche
**aucune** invalidation en amont. Interdit n° 1 : une relance de tome coûte des heures de GPU,
et `load_regions` rend `None` sur écart de version, ce qui déclencherait
`downstream("detection")` sur tous les projets. `--phase` n'est pas `--from` : deux mécaniques
distinctes, deux noms distincts.

## Le schéma a changé au lot 26, et un fichier d'avant se relit

`VERSION` passe de 1 à 2. Trois champs deviennent structurés :

| v1 | v2 | pourquoi |
|---|---|---|
| `references: [chemin]` | `references: [{fichier, motif, retenue}]` | un utilisateur qui retire une image doit voir **pourquoi** elle avait été prise (`PLAN-26` L26.0, règle 3) |
| — | `ancrages_style: [{…}]` | deux usages du même canal d'images ; les mélanger produit une image dont on ne sait pas ce qui a raté |
| `entites`, `image_controle` | `canaux: {entites, image_de_controle}` | ce ne sont pas du texte, ce sont des **arguments typés** du moteur, et les ranger ensemble le dit |

⚠ **`fill_defaults` relit les deux formes**, et un fichier v1 validé ne redemande pas de
validation : le champ `valide` est conservé tel quel. Un schéma qui invaliderait la relecture
humaine à chaque lot rendrait la porte insupportable, donc contournée.

## Ce que la phase 1 remplit, et ce qui vient d'où

`depuis_oeuvre` assemble, personnage par personnage :

- le **prompt**, par `illustration/prompt.py:construire` — charpente déterministe, attributs
  cités de la bible, sujet accordé par le glossaire ;
- la **sélection d'images**, par `illustration/selection.py` — un motif par image, retenue
  comme écartée, plafond du lot 25 appliqué ;
- `attributs_sources`, la traçabilité : d'où vient chaque mot du prompt.

⚠ **Le LLM est facultatif et il n'entre pas ici.** `depuis_oeuvre` est pur : il reçoit une
sélection et des clauses de scène déjà calculées. C'est ce qui le rend testable en CI sans
serveur, et c'est aussi ce qui rend le balayage des formes de texte comparable.
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import yaml

from illustration import gabarits as gabarits_mod
from illustration import prompt as prompt_mod
from illustration import selection as selection_mod
from illustration.moteur import HAUTEUR_DEFAUT, LARGEUR_DEFAUT, Entite, Requete

#: Version du schéma du fichier. Sans rapport avec `checkpoints.FORMAT_VERSION` — cf. la
#: docstring : ce fichier n'invalide aucun cache et n'en est pas un.
VERSION = 2

NOM_FICHIER = "requete.yaml"

#: Motif inscrit sur une référence héritée d'un `requete.yaml` d'avant le lot 26. Il dit la
#: vérité — personne n'a écrit de motif — plutôt que d'en inventer un plausible.
MOTIF_HERITE = "(requête écrite avant le lot 26 : aucun motif n'a été enregistré)"


class RequeteNonValidee(RuntimeError):
    """La phase image a été lancée sur une requête que personne n'a validée, ou dont la
    relecture humaine a retiré ce qui la rendait défendable."""


_ENTETE = """\
# ============================================================
#  Requête d'illustration — {projet} / {tome}
#  Écrit par la PHASE 1. Relu, corrigé et validé par un humain.
#  Lu par la PHASE 2, qui REFUSE de démarrer tant que
#  `valide` vaut false. C'est le seul garde-fou qui garantisse
#  qu'aucune image n'existe sans qu'un humain ait validé le
#  prompt qui l'a produite.
#
#  Ce fichier n'est PAS un checkpoint : le supprimer n'invalide
#  aucun cache et ne relance aucune étape en amont.
#
#  Généré le {date} par Angelith {version}.
#
#  ── CE QUE TU DOIS RELIRE, DANS CET ORDRE ────────────────────
#
#  1. `references:` — est-ce la BONNE PERSONNE ? Chaque image
#     porte son `motif` : pourquoi elle a été prise, ou pourquoi
#     elle a été écartée. Passe `retenue` à false pour en
#     retirer une, à true pour en reprendre une.
#     ⚠ Tu ne peux pas toutes les retirer : sans référence, la
#     phase 2 retombe sur de la génération pure, et elle refuse.
#
#  2. `ancrages_style:` — le REGISTRE du tome, pas l'identité.
#     Préfère une image SANS visage : une ancre qui montre
#     quelqu'un peut le faire apparaître dans l'image produite.
#
#  3. `prompt:` — dit-il ce que tu veux voir ? Corrige librement.
#     `attributs_sources` te dit d'où vient chaque mot ; ouvre
#     le fichier cité si un attribut te surprend.
#
#  4. `prompt_negatif:` — chaque terme a un motif, écrit dans
#     illustration/gabarits/{gabarit}.yaml. En retirer un est un
#     CHOIX, pas une faute.
#
#  5. `graine:` — null = aléatoire, un entier = reproductible.
#     Tu peux la vider sans rien casser.
#
#  Puis : renseigne `validation.par`, passe `valide` à true, et
#    python run_illustration.py "{projet}" {tome} --phase image
#
#  ⚠ Le nom de l'œuvre ne doit PAS entrer dans un prompt : il
#  finirait dans les métadonnées du PNG, et la phase 2 lèvera.
# ============================================================

"""


def vide(modele: str = "") -> dict:
    return {"version": VERSION, "valide": False,
            "validation": {"par": "", "date": "", "prompt_initial": {},
                           "references_initiales": {}},
            "modele": modele,
            "forme": "prose", "langue": "fr", "gabarit": gabarits_mod.DEFAUT,
            "phase1": {"secondes": 0.0, "appels_llm": 0, "plafonds_atteints": []},
            "images": []}


def image_vide(nom: str = "") -> dict:
    """Un bloc d'image, TOUS champs écrits même vides — comme le glossaire et la bible, et
    pour la même raison : ce qui est visible se corrige, ce qui est absent s'oublie."""
    return {"nom": nom, "personnage": "", "cadrage": prompt_mod.CADRAGE_DEFAUT,
            # ⚠ `PLAN-29` L29.4 : la variante de décor. Défaut `neutre` — **le comportement
            # d'avant le lot 29, mot pour mot**. Le levier existe pour que la mesure de la
            # part d'aplats puisse être faite ; il ne déplace rien tant qu'elle ne l'est pas.
            "decor": gabarits_mod.DECOR_DEFAUT,
            "prompt": "", "prompt_negatif": "",
            "references": [], "ancrages_style": [], "attributs_sources": [],
            "largeur": LARGEUR_DEFAUT, "hauteur": HAUTEUR_DEFAUT,
            "graine": None, "nombre_images": 1, "pas": 30, "guidage": 4.0,
            "canaux": {"entites": [], "image_de_controle": None}}


def chemin(dossier) -> Path:
    return Path(dossier) / NOM_FICHIER


# ────────────────────────────  Lecture / écriture  ────────────────────────────

def load(source) -> dict:
    p = Path(source)
    if not p.is_file():
        return vide()
    with open(p, encoding="utf-8") as fh:
        brut = yaml.safe_load(fh) or {}
    if not isinstance(brut, dict):
        return vide()
    return fill_defaults(brut)


def fill_defaults(doc: dict) -> dict:
    brut = dict(doc or {})
    validation = dict(brut.get("validation") or {})
    phase1 = dict(brut.get("phase1") or {})
    sortie = {
        "version": VERSION,
        "valide": bool(brut.get("valide")),
        "validation": {"par": str(validation.get("par") or ""),
                       "date": str(validation.get("date") or ""),
                       "prompt_initial": dict(validation.get("prompt_initial") or {}),
                       "references_initiales":
                           dict(validation.get("references_initiales") or {})},
        "modele": str(brut.get("modele") or ""),
        "forme": str(brut.get("forme") or "prose"),
        "langue": str(brut.get("langue") or "fr"),
        "gabarit": str(brut.get("gabarit") or gabarits_mod.DEFAUT),
        "phase1": {"secondes": float(phase1.get("secondes") or 0.0),
                   "appels_llm": int(phase1.get("appels_llm") or 0),
                   "plafonds_atteints": list(phase1.get("plafonds_atteints") or [])},
        "images": [_fill_image(i) for i in (brut.get("images") or [])
                   if isinstance(i, dict)],
    }
    for cle, valeur in brut.items():
        if cle not in sortie:
            sortie[cle] = valeur
    return sortie


def _fill_image(bloc: dict) -> dict:
    base = image_vide(str(bloc.get("nom") or ""))
    for cle in ("personnage", "prompt", "prompt_negatif"):
        base[cle] = str(bloc.get(cle) or "")
    base["cadrage"] = str(bloc.get("cadrage") or prompt_mod.CADRAGE_DEFAUT)
    # ⚠ Un `requete.yaml` écrit avant le lot 29 n'a pas de `decor`, et il retombe donc sur
    # `neutre` — c'est-à-dire exactement la phrase qu'il portait déjà dans son prompt. Un
    # fichier validé ne redemande pas de validation pour ce champ (cf. la docstring du
    # module : « un schéma qui invaliderait la relecture humaine à chaque lot rendrait la
    # porte insupportable, donc contournée »).
    base["decor"] = str(bloc.get("decor") or gabarits_mod.DECOR_DEFAUT)
    base["references"] = _images_choisies(bloc.get("references"))
    base["ancrages_style"] = _images_choisies(bloc.get("ancrages_style"))
    base["attributs_sources"] = [dict(a) for a in (bloc.get("attributs_sources") or [])
                                 if isinstance(a, dict)]
    base["canaux"] = _canaux(bloc)
    for cle, defaut in (("largeur", LARGEUR_DEFAUT), ("hauteur", HAUTEUR_DEFAUT),
                        ("pas", 30), ("nombre_images", 1)):
        base[cle] = int(bloc.get(cle) if bloc.get(cle) is not None else defaut)
    # ⚠ `graine: null` est une VALEUR — « aléatoire » —, pas une absence. La confondre avec
    # 0 rendrait une requête reproductible là où l'utilisateur a demandé le contraire.
    base["graine"] = None if bloc.get("graine") is None else int(bloc["graine"])
    base["guidage"] = float(bloc.get("guidage") if bloc.get("guidage") is not None else 4.0)
    for cle, valeur in bloc.items():
        if cle not in base and cle not in ("entites", "image_controle"):
            base[cle] = valeur
    return base


def _images_choisies(brut) -> list:
    """Normalise les deux formes : `[chemin]` (v1) et `[{fichier, motif, retenue}]` (v2).

    ⚠ Une entrée v1 est reprise **retenue**, avec `MOTIF_HERITE`. Elle l'était de fait — la
    phase 2 du lot 25 envoyait toutes les références du fichier — et le motif dit la vérité
    plutôt que d'en inventer un : personne n'en avait écrit."""
    sorties = []
    for entree in (brut or []):
        if isinstance(entree, str):
            if entree.strip():
                sorties.append({"fichier": entree, "motif": MOTIF_HERITE, "retenue": True,
                                "par": "herite"})
            continue
        if not isinstance(entree, dict):
            continue
        fichier = str(entree.get("fichier") or "")
        if not fichier:
            continue
        bloc = {"fichier": fichier,
                "motif": str(entree.get("motif") or MOTIF_HERITE),
                "retenue": bool(entree.get("retenue", True)),
                "par": str(entree.get("par") or "deterministe")}
        if entree.get("visage") is not None:
            bloc["visage"] = bool(entree["visage"])
        sorties.append(bloc)
    return sorties


def _canaux(bloc: dict) -> dict:
    """Le bloc `canaux`, en acceptant les champs v1 `entites` / `image_controle`.

    ⚠ Ces canaux sont livrés **DÉSARMÉS** : listes vides et `null`. L'étape 0.4 du `PLAN-26`
    demande de n'en livrer **qu'un**, celui dont l'apport est mesuré, et de livrer désarmé
    tout canal non mesuré. Le champ existe pour que l'inventaire soit visible dans le
    fichier que l'utilisateur relit ; il ne s'arme qu'en l'écrivant à la main, et le moteur
    refusera alors le canal si le graphe ne le porte pas (`moteur.verifier_canaux`)."""
    brut = dict(bloc.get("canaux") or {})
    entites = brut.get("entites")
    if entites is None:
        entites = bloc.get("entites")
    controle = brut.get("image_de_controle")
    if controle is None:
        controle = bloc.get("image_controle") or None
    return {
        "entites": [{"prompt": str(e.get("prompt") or ""),
                     "masque": str(e.get("masque") or "")}
                    for e in (entites or []) if isinstance(e, dict)],
        "image_de_controle": str(controle) if controle else None,
    }


def save(doc: dict, destination, *, projet: str = "", tome: str = "") -> Path:
    """Écrit le fichier avec sa bannière. L'en-tête est réécrit à chaque fois : c'est un mode
    d'emploi, pas une donnée, et un utilisateur qui rouvre le fichier six mois plus tard doit
    y retrouver la marche à suivre."""
    from core.version import __version__

    p = Path(destination)
    rempli = fill_defaults(doc)
    p.parent.mkdir(parents=True, exist_ok=True)
    entete = _ENTETE.format(projet=projet or p.parent.parent.name, tome=tome or p.parent.name,
                            date=datetime.now(timezone.utc).strftime("%Y-%m-%d"),
                            version=__version__, gabarit=rempli["gabarit"])
    corps = yaml.safe_dump(rempli, allow_unicode=True, sort_keys=False, width=100)
    p.write_text(entete + corps, encoding="utf-8")
    return p


# ─────────────────────────────────  La porte  ─────────────────────────────────

def exiger_validation(doc: dict) -> None:
    """Lève `RequeteNonValidee` tant que la porte humaine n'est pas franchie, **avec le motif**.

    Deux motifs distincts, et ils ne se confondent pas : « personne n'a validé » et « la
    validation ne dit pas qui ». Le second existe parce que le sidecar de provenance doit
    porter un nom — c'est la ligne exacte que la politique IA du dossier NLnet exige de
    pouvoir montrer, et « validé par (vide) » ne la montre pas."""
    doc = fill_defaults(doc)
    if not doc["valide"]:
        raise RequeteNonValidee(
            f"{NOM_FICHIER} porte `valide: false` — la phase image ne démarre pas.\n"
            f"  Ce n'est pas un défaut de configuration : c'est le garde-fou. Relis le "
            f"fichier, corrige les prompts, renseigne `validation.par`, puis passe `valide` "
            f"à true. Aucune clé de config ne contourne cette porte, et il n'y a pas de mode "
            f"« tout automatique », même derrière un drapeau.")
    if not doc["validation"]["par"].strip():
        raise RequeteNonValidee(
            f"{NOM_FICHIER} est validé mais `validation.par` est vide.\n"
            f"  Le sidecar de provenance de chaque image doit dire QUI a validé le prompt : "
            f"c'est ce qui distingue « assisté » de « généré ». Écris ton nom.")
    if not doc["images"]:
        raise RequeteNonValidee(
            f"{NOM_FICHIER} ne contient aucune image à produire — rien à faire.")


def exiger_references_retenues(doc: dict) -> None:
    """Le **second battant** de la porte : on ne peut pas vider ce que la phase 1 avait retenu.

    ⚠ **`graine` et `attributs_sources` se vident sans rien casser** — ce sont une commodité
    et une documentation. `references` non : la phase 2 sans référence retombe sur de la
    génération pure, ce que le `PLAN-25` L25.2 refuse déjà à un autre endroit du code. Le
    `PLAN-26` L26.2 bis demande que le refus se dise **aussi ici, à la lecture du fichier,
    avec le motif nommé** — donc avant la bascule VRAM, avant le chargement de 12 Go de
    poids, et avant la première seconde de GPU.

    ⚠ **Le refus porte sur ce que la RELECTURE a retiré, pas sur une absence d'origine**, et
    la distinction est la raison d'être de `validation.references_initiales`. Deux situations
    se ressemblent dans le fichier et ne se ressemblent pas du tout dans la vie :

    | dans le fichier | ce que ça veut dire | qui refuse |
    |---|---|---|
    | la phase 1 avait retenu, l'humain a tout décoché | « je ne veux plus de références » | **ici**, tout de suite |
    | la phase 1 n'avait rien retenu | le personnage n'a aucune référence validée dans la bible | `identite.SansReferenceValidee`, qui le nomme mieux — et qui refuse cette IMAGE, pas le run |

    Les confondre ferait échouer un run entier pour un personnage que la bible ne documente
    pas — exactement le cas majoritaire du corpus réel, où 7 personnages sur 11 n'ont aucune
    référence validée."""
    doc = fill_defaults(doc)
    initiales = doc["validation"]["references_initiales"] or {}
    vides = [bloc["nom"] for bloc in doc["images"]
             if (initiales.get(bloc["nom"]) or [])
             and not any(r["retenue"] for r in bloc["references"])]
    if not vides:
        return
    raise RequeteNonValidee(
        f"{NOM_FICHIER} : toutes les références ont été décochées pour "
        f"{', '.join(f'« {n} »' for n in vides)}, alors que la phase 1 en avait retenu.\n"
        f"  Sans référence, la phase 2 retomberait sur de la génération pure : le modèle "
        f"inventerait un visage au lieu de suivre celui de l'œuvre. Le lot 25 refuse déjà "
        f"ce cas plus loin dans le run ; le refuser ici évite de décharger le LLM et de "
        f"charger 12 Go de poids pour rien.\n"
        f"  Repasse au moins une `retenue` à true, ou retire le bloc d'image entier si tu "
        f"ne veux pas de ce personnage.")


def verifier(doc: dict, *, racine_projet=None) -> list[str]:
    """Les incohérences, en clair. Liste vide = rien à signaler. N'écrit rien, ne corrige rien.

    Le contrôle des fichiers de référence n'a lieu que si `racine_projet` est donné ; sinon on
    ne prétend pas les avoir vérifiés.

    ⚠ `racine_projet` est `build/<Projet>/`, **l'ŒUVRE et pas un tome**, et il change le
    RÉSULTAT : la bible est par projet, donc ses références couvrent plusieurs volumes — sur
    le tome de référence, 7 des 10 références vivent dans le Vol.2. La résolution est déléguée
    à `core.bible.reference_existe`, qui est LA règle du dépôt ; en écrire une seconde ici a
    été le défaut, corrigé le 2026-08-29. Le paramètre `dossier_tome` a disparu le
    2026-08-31 : il désignait une racine trop étroite, et en garder deux invitait à les
    confondre."""
    doc = fill_defaults(doc)
    problemes: list[str] = []
    noms = [i["nom"] for i in doc["images"]]
    for double in sorted({n for n in noms if noms.count(n) > 1}):
        problemes.append(f"deux images portent le nom « {double} » — la seconde écraserait "
                         f"la première")
    if doc["forme"] not in gabarits_mod.FORMES:
        problemes.append(f"forme de champ texte inconnue : « {doc['forme']} » "
                         f"(attendu : {', '.join(gabarits_mod.FORMES)})")
    if doc["langue"] not in gabarits_mod.LANGUES:
        problemes.append(f"langue de prompt inconnue : « {doc['langue']} » "
                         f"(attendu : {', '.join(gabarits_mod.LANGUES)})")
    for bloc in doc["images"]:
        problemes.extend(_verifier_bloc(bloc, racine_projet))
    return problemes


def _verifier_bloc(bloc: dict, racine_projet) -> list:
    nom = bloc["nom"] or "(sans nom)"
    problemes: list[str] = []
    if not bloc["nom"].strip():
        problemes.append("une image n'a pas de `nom` : il sert de nom de fichier")
    if not bloc["prompt"].strip() and not _retenues(bloc["references"]):
        problemes.append(f"« {nom} » n'a ni prompt ni référence retenue — le moteur n'aurait "
                         f"rien à honorer")
    for cote in ("largeur", "hauteur"):
        if bloc[cote] <= 0:
            problemes.append(f"« {nom} » : {cote} = {bloc[cote]}")
    if bloc["pas"] <= 0:
        problemes.append(f"« {nom} » : pas = {bloc['pas']}")
    if bloc["nombre_images"] <= 0:
        problemes.append(f"« {nom} » : nombre_images = {bloc['nombre_images']}")
    for choix in bloc["references"] + bloc["ancrages_style"]:
        if not str(choix.get("motif") or "").strip():
            # Règle 3 du PLAN-26 L26.0 : sans motif, la porte humaine se réduit à un clic de
            # confiance. Un motif vide est donc une incohérence, pas un détail cosmétique.
            problemes.append(f"« {nom} » : l'image {choix['fichier']} n'a pas de `motif` — "
                             f"un utilisateur ne peut pas juger un choix qu'on ne lui "
                             f"explique pas")
    if racine_projet is None:
        return problemes
    for choix in _retenues(bloc["references"]) + _retenues(bloc["ancrages_style"]):
        chemins = _chemins_de(choix["fichier"], racine_projet)
        if not chemins:
            problemes.append(f"« {nom} » : image retenue introuvable — {choix['fichier']}")
        elif len(chemins) > 1:
            # ⚠ **Une référence AMBIGUË est une incohérence, pas un détail.** `media/image1.png`
            # sur une œuvre dont deux tomes portent un `image1` répond deux fois, et jusqu'au
            # 2026-08-31 le premier gagnait en silence — c'est-à-dire qu'on pouvait envoyer au
            # modèle le personnage d'un autre volume que celui qu'on croyait.
            problemes.append(
                f"« {nom} » : référence AMBIGUË — « {choix['fichier']} » existe dans "
                f"{len(chemins)} tomes ({', '.join(c.parent.parent.name for c in chemins)}). "
                f"Préfixe-la par son tome : « {chemins[0].parent.parent.name}/"
                f"{Path(choix['fichier']).name} »")
    for entite in bloc["canaux"]["entites"]:
        masque = entite.get("masque") or ""
        if masque and not _chemins_de(masque, racine_projet):
            problemes.append(f"« {nom} » : masque introuvable — {masque}")
    controle = bloc["canaux"]["image_de_controle"]
    if controle and not _chemins_de(controle, racine_projet):
        problemes.append(f"« {nom} » : image de contrôle introuvable — {controle}")
    return problemes


def _chemins_de(reference: str, racine_projet) -> list:
    """Tous les chemins auxquels cette référence répond. Une seule règle, celle de la bible."""
    from core import bible
    return bible.chemins_de_reference(reference, racine_projet)


def _retenues(choisies) -> list:
    return [c for c in (choisies or []) if c.get("retenue")]


def images_retenues(bloc: dict) -> tuple[list, list]:
    """`(références d'identité retenues, ancres de style retenues)`, dans l'ordre du fichier.

    ⚠ **L'ORDRE COMPTE et il n'est pas cosmétique.** Le prompt désigne les images par leur
    rang — « le personnage est celui de l'image 1 », « suis le style graphique de l'image 3 ».
    Les ancres passent donc **après** les références, toujours, et changer cet ordre sans
    changer le texte ferait suivre au modèle le style d'un portrait et l'identité d'un décor."""
    return _retenues(bloc.get("references")), _retenues(bloc.get("ancrages_style"))


def requetes(doc: dict) -> list[tuple[str, Requete]]:
    """`[(nom de l'image, Requete)]`, dans l'ordre du fichier.

    ⚠ **Seules les images `retenue: true` entrent dans le canal.** Une image écartée reste
    dans le fichier avec son motif — c'est ce qui permet à l'utilisateur de la reprendre —
    mais elle ne part pas au moteur. Confondre « présente dans le fichier » et « envoyée au
    modèle » viderait la relecture humaine de son effet."""
    doc = fill_defaults(doc)
    modele = doc["modele"]
    sortie: list[tuple[str, Requete]] = []
    for bloc in doc["images"]:
        references, ancrages = images_retenues(bloc)
        canaux = bloc["canaux"]
        sortie.append((bloc["nom"], Requete(
            prompt=bloc["prompt"], prompt_negatif=bloc["prompt_negatif"],
            references=tuple(c["fichier"] for c in references + ancrages),
            entites=tuple(Entite(prompt=e["prompt"], masque=e["masque"])
                          for e in canaux["entites"]),
            image_controle=canaux["image_de_controle"] or "",
            largeur=bloc["largeur"], hauteur=bloc["hauteur"],
            graine=_graine(bloc), pas=bloc["pas"], guidage=bloc["guidage"],
            modele=modele)))
    return sortie


def _graine(bloc: dict) -> int:
    """`null` = aléatoire, et **c'est tiré ici, une fois**, pas dans le moteur.

    ⚠ La graine effective doit entrer dans le payload, donc dans l'empreinte, donc dans le
    sidecar : sans elle, `--rejouer` ne pourrait pas reproduire l'image, et la traçabilité
    est une exigence écrite du dossier de financement. Un moteur qui tirerait sa graine
    lui-même rendrait le rejeu impossible sans que rien ne le signale."""
    import secrets

    if bloc.get("graine") is not None:
        return int(bloc["graine"])
    return secrets.randbelow(2 ** 31)


# ───────────────────────  Le squelette, depuis l'œuvre  ───────────────────────

def depuis_oeuvre(bible_doc: dict, glossaire: dict | None = None, *, modele: str = "",
                  graine: int | None = 0, personnages=None,
                  selections: dict | None = None, scenes: dict | None = None,
                  cadrage: str = prompt_mod.CADRAGE_DEFAUT,
                  decor: str = gabarits_mod.DECOR_DEFAUT, forme: str = "prose",
                  langue: str = "fr", gabarit: str = gabarits_mod.DEFAUT,
                  budget: prompt_mod.Budget | None = None) -> dict:
    """Un `requete.yaml` **déterministe**, un bloc par personnage descriptible.

    Un personnage est **descriptible** s'il porte au moins un attribut CITÉ. Un personnage
    sans attribut cité n'entre pas dans la requête : générer son portrait serait inventer, et
    c'est exactement ce que la règle de citation de la bible refuse.

    `selections` est `{personnage: Selection}` — le choix d'images de `illustration/
    selection.py`, fait avant l'appel (avec ou sans LLM). `scenes` est
    `{personnage: clause de scène}` — reformulée par le LLM, et **filtrée ici** par
    `prompt.epurer`.

    ⚠ **Aucun réseau n'est ouvert dans cette fonction**, et c'est ce qui la rend testable en
    CI sans serveur et comparable d'un balayage à l'autre."""
    doc = vide(modele=modele)
    doc.update({"forme": forme, "langue": langue, "gabarit": gabarit})
    budget = budget or prompt_mod.Budget()
    voulus = {str(n) for n in personnages} if personnages else None
    mots_style = mots_de_style(bible_doc, langue=langue, gabarit=gabarit)
    selections = selections or {}

    candidats = []
    for entree in (bible_doc or {}).get("personnages") or []:
        if not isinstance(entree, dict):
            continue
        nom = str(entree.get("nom") or "").strip()
        if not nom or (voulus is not None and nom not in voulus):
            continue
        candidats.append(nom)

    for nom in budget.retenir(candidats):
        choix = selections.get(nom) or selection_mod.Selection()
        references = choix.retenues(selection_mod.USAGE_IDENTITE)
        ancrages = choix.retenues(selection_mod.USAGE_ANCRAGE)
        try:
            construction = prompt_mod.construire(
                nom, bible_doc, glossaire, cadrage=cadrage, decor=decor, forme=forme,
                langue=langue,
                gabarit=gabarit, passage=scenes.get(nom) if scenes else None,
                style=mots_style, nombre_references=len(references),
                nombre_ancrages=len(ancrages))
        except prompt_mod.PersonnageIndescriptible:
            # ⚠ Le refus porte sur CE personnage, pas sur le run. Sur le corpus réel, la
            # bible déclare 11 personnages dont plusieurs ne portent qu'un attribut ; faire
            # échouer le run entier pousserait à contourner la règle de citation.
            continue
        bloc = image_vide(_ardoise(nom))
        bloc.update({
            "personnage": nom, "cadrage": cadrage, "decor": decor,
            "prompt": construction.requete.prompt,
            "prompt_negatif": construction.requete.prompt_negatif,
            "references": [c.payload() for c in choix.references],
            "ancrages_style": [c.payload() for c in choix.ancrages],
            "attributs_sources": construction.attributs_sources(),
            "graine": None if graine is None else int(graine)})
        doc["images"].append(bloc)

    doc["phase1"] = {
        "secondes": round(sum(s.secondes for s in selections.values()), 3),
        "appels_llm": sum(s.appels_llm for s in selections.values()),
        "plafonds_atteints": list(budget.atteints)}
    return doc


def mots_de_style(bible_doc: dict, *, langue: str = "fr",
                  gabarit: str = gabarits_mod.DEFAUT) -> str:
    """Les mots de registre graphique : ceux de l'HUMAIN, puis ceux de la MESURE.

    ⚠ **L'ordre n'est pas cosmétique.** `bible.style.mots` est écrit à la main par quelqu'un
    qui a regardé le tome ; la signature est ce que `core/illustrations.py` y a mesuré. Quand
    les deux se contredisent, c'est l'humain qui est en tête du prompt — comme partout
    ailleurs dans cette brique.

    ⚠ **Sur le corpus de référence, `bible.style.mots` est VIDE**, et c'est ce qui rend cette
    fonction utile : sans elle, l'approche 1 de l'étape 0.2 n'ajouterait aujourd'hui aucun mot,
    et la mesurer reviendrait à mesurer l'approche 3 deux fois."""
    style = (bible_doc or {}).get("style") or {}
    a_la_main = str(style.get("mots") or "").strip()
    mesures = prompt_mod.mots_de_signature(
        style.get("signature") or {}, gabarits_mod.charger(gabarit, langue=langue))
    return ", ".join(m for m in (a_la_main, mesures) if m)


def archiver_l_initial(doc: dict) -> dict:
    """Archive le prompt et les références **avant** toute correction humaine.

    Le sidecar doit pouvoir montrer l'avant et l'après : c'est ce que la traçabilité exige,
    et c'est aussi ce qui rend `exiger_references_retenues` lisible — « tu as décoché ce que
    la phase 1 avait retenu » se dit mieux avec la liste d'origine sous les yeux."""
    doc["validation"]["prompt_initial"] = {b["nom"]: b["prompt"] for b in doc["images"]}
    doc["validation"]["references_initiales"] = {
        b["nom"]: [c["fichier"] for c in _retenues(b["references"])]
        for b in doc["images"]}
    return doc


def _ardoise(nom: str) -> str:
    """Un nom de fichier sûr, dérivé du nom du personnage.

    ⚠ Il porte le nom du PERSONNAGE, jamais celui de l'œuvre : un nom de personnage seul
    n'identifie pas un titre, et il faut bien que l'utilisateur retrouve ses images. C'est le
    même arbitrage que `sources/` — qui est exclu de git en bloc, ce dossier aussi."""
    garde = [c if (c.isalnum() or c in "-_") else "-" for c in nom.strip().casefold()]
    return "-".join(part for part in "".join(garde).split("-") if part) or "image"
