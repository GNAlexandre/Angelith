# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Alexandre Tournel

"""**La voie A** du `PLAN-25` : conditionner la génération par les références de la bible.

    bible.references[role: identite]  →  recadrées, redimensionnées  →  canal `references`
    bible.style.ancrages              →  l'échelle de STYLE du juge
    bible.style.signature             →  l'échelle de style DÉTERMINISTE

## Ce que ce module fait, et ce qu'il refuse de faire

Il prépare les images de référence pour le canal `references` du moteur, il mesure les
**trois grandeurs** (`illustration/juge.py`) sur chaque image produite, et il **refuse** —
avec un motif nommé — quand la mesure ne soutient pas de produire.

⚠ **Il ne prépare une référence qu'à partir de `confiance: humaine`.** `core/bible.py` range
les confiances en `proposee` / `llm` / `humaine` et note que « seule la dernière compte dans
la couverture de référence du banc » ; générer le portrait d'un personnage sur une image que
personne n'a regardée serait exactement ce que la règle de citation de la bible refuse pour
un attribut.

## Les quatre motifs de L25.2, et lesquels sont ARMÉS

| Motif | Effet | Armé ? |
|---|---|---|
| `sans_reference_validee` | **refus** — aucune image produite | ✅ oui, et il n'a pas d'interrupteur |
| `nouveaute_insuffisante` | **rejet** de l'image produite | ✅ oui — le plan écrit « ce cas n'est pas négociable » |
| `ressemblance_faible` | l'image est produite et **marquée** | ✅ oui, en signalement seulement |
| `style_hors_registre` | l'image est produite et **marquée**, avec le descripteur qui décroche | ✅ en signalement, ❌ **jamais en rejet** |

⚠ **Le rejet automatique sur le style n'est PAS armé, et c'est une mesure qui le décide.** Le
critère 4 bis du plan l'autorise « seulement si la mesure le soutient ». Elle ne le soutient
pas : l'échelle de style mesurée sur le corpus réel sépare mal (cf.
`docs/mesures/identite-2026-08-29.md` §2). Le dépôt livre désarmé ce que la mesure ne soutient
pas — même règle que `manga.onomatopees.effacement.mode: "aucun"` au lot 22 et que
`illustration.vram.decharger_image` au lot 24.

## Le recadrage : le mécanisme est livré, l'axe n'est pas mesuré — **au 2026-09-02**

Le `PLAN-25` L25.1 demande de balayer la **nature du recadrage** — visage seul, buste, corps
entier — parce que c'est le chiffre qui dit ce que le `PLAN-23` L23.5 doit demander à
l'utilisateur de recadrer.

⚠ **Cet axe n'a pas pu être mesuré, et la cause est dans le corpus, pas dans le code.** La
bible réelle porte des références qui sont des **pages entières** (`media/…_p23_x330.jpeg`),
sans boîte de recadrage : `core/bible.py` n'avait pas de champ pour en porter une. Le champ
`cadre` est ajouté ici — quatre fractions `[x, y, largeur, hauteur]` relatives, donc stables
quelle que soit la résolution du fichier — et il reste **vide sur les 10 références du corpus
réel**. Balayer un axe dont toutes les valeurs sont identiques ne mesure rien, et fabriquer
des recadrages nous-mêmes reviendrait à inventer la validation humaine que le champ exige.
Le dire vaut mieux que de publier une colonne à une seule valeur.

⚠ **Et l'axe non mesuré est exactement celui que le premier usage réel désigne.** Les trois
premières références validées du corpus sont **trois couvertures de light novel** ; conditionner
sur une page entière fait reproduire au modèle la **composition de la page** plutôt que le seul
personnage. Le recadrage n'est donc pas un raffinement de l'axe : c'en est le prérequis
manquant. Cf. `Reference.couverture` et `retenir`.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from core import bible as bible_mod

#: Nombre maximal d'images de référence envoyées au moteur. 3 est ce que le nœud
#: `TextEncodeQwenImageEditPlus` de ComfyUI 0.34.2 expose (`image1`, `image2`, `image3`) —
#: ce n'est pas un réglage de prudence, c'est le maximum du graphe livré.
REFERENCES_MAX = 3

#: Côté de la référence préparée. Le modèle ramène de toute façon ses entrées à une aire
#: fixe ; envoyer 6 Mpx par référence coûterait du temps d'encodage pour rien.
COTE_REFERENCE = 1024

#: Sous-dossier de la brique où les références préparées sont écrites. **Dans le périmètre**
#: de `illustration/frontiere.py` : les originaux de `media/` ne sont jamais touchés.
DOSSIER_REFERENCES = "references"

#: ⚠ **UNE GARANTIE DU DÉPÔT A UNE FAILLE, ET ELLE EST NOMMÉE ICI PLUTÔT QUE TUE.**
#:
#: `illustration/marquage.py:_sans_titre` refuse d'écrire le titre de l'œuvre dans les
#: métadonnées d'un PNG, et lève plutôt que de censurer. Il inspecte du **texte** : le prompt,
#: le prompt négatif, l'identifiant, le nom du modèle.
#:
#: Il ne voit pas un titre **peint dans une image**. Or la voie A envoie au modèle des
#: références qui sont, sur le corpus réel, des **couvertures de light novel** portant le titre,
#: le nom de l'auteur et celui de l'illustrateur en grandes lettres. Ces pixels partent chez
#: ComfyUI, entrent dans le conditionnement, et **rien n'empêche le modèle de les reproduire**
#: dans l'image générée.
#:
#: Ce qui est fait : `retenir` repousse les couvertures en dernier (cf. sa docstring), et le
#: fait est écrit ici, dans `docs/mesures/identite-2026-08-29.md` et dans le rapport de la
#: brique. Ce qui n'est **pas** fait : aucune détection de texte n'est appliquée aux
#: références. Le dépôt en a une (`manga/text_detection.py`), mais `illustration/` n'importe
#: que `core/` — c'est une contrainte d'architecture testée, pas un oubli — et la contourner
#: coûterait plus que ce que ce lot peut mesurer. Le dire vaut mieux que de laisser croire le
#: garde universel.
TITRE_DANS_LES_PIXELS = (
    "le titre de l'œuvre peut être PEINT dans une image de référence (couverture) ; le garde "
    "de marquage inspecte du texte, pas des pixels")

#: Les motifs, nommés et comptés — convention du dépôt (`manga/detection_retry.py`).
MOTIFS_LISIBLES = {
    "sans_reference_validee": "aucune référence validée par un humain pour ce personnage",
    "nouveaute_insuffisante": "l'image est trop proche de sa référence la plus proche — "
                              "c'est une reproduction, pas une illustration inédite",
    "ressemblance_faible": "la ressemblance est sous le plancher de confusion du juge",
    "style_hors_registre": "les descripteurs de l'image sortent de l'échelle du tome",
    "juge_indisponible": "aucun encodeur : les trois grandeurs ne sont pas mesurées",
    "juge_inutilisable": "le juge ne sépare pas « même personnage » de « personnages "
                         "différents » sur ce corpus — ses verdicts ne sont pas opposables",
}


class SansReferenceValidee(RuntimeError):
    """Un personnage sans référence validée par un humain. **Aucune image n'est produite.**

    ⚠ Ce n'est pas un avertissement et il n'y a pas de mode « au mieux ». Le patron est celui
    du refus d'accord incertain de `manga/relecture.py` : produire quand même une image
    plausible ferait passer une invention pour une illustration de l'œuvre."""


# ─────────────────────────  Les références, de la bible au moteur  ─────────────────────────

@dataclass(frozen=True)
class Reference:
    """Une référence d'identité résolue sur le disque, prête à être préparée."""

    fichier: str
    source: Path
    confiance: str = "proposee"
    contexte: str = ""
    #: `[x, y, largeur, hauteur]` en fractions de l'image, ou `()` si la référence est la
    #: page entière. Cf. la docstring du module : le champ existe, le corpus ne le remplit pas.
    cadre: tuple = ()
    #: La classe que `core/illustrations.py` donne à ce fichier — `couverture`,
    #: `pleine_page`… `""` si le tome n'a pas été inventorié.
    classe: str = ""

    @property
    def validee(self) -> bool:
        return self.confiance == "humaine"

    @property
    def couverture(self) -> bool:
        """Une couverture est une **mauvaise référence d'identité**, et ce n'est pas un avis.

        ⚠ `core/illustrations.py:ancrages_proposes` le dit déjà pour le style — « une
        couverture porte un logo d'éditeur et un bandeau de prix ; aucun descripteur ne le
        sait, et elle ferait une mauvaise ancre ». Mesuré le 2026-08-29, ça vaut **au moins
        autant pour l'identité**, et pour une raison de plus : la couverture d'un light novel
        porte le **titre de l'œuvre en grandes lettres**. Le modèle d'édition reçoit ces
        pixels et peut les reproduire — voir `TITRE_DANS_LES_PIXELS` ci-dessous."""
        return self.classe == "couverture"


def references_de(bible_doc: dict, nom: str, racine_projet) -> list[Reference]:
    """Les références d'identité d'un personnage, résolues sur le disque, dans l'ordre du
    fichier.

    ⚠ La résolution passe par `core.bible.reference_existe` — **la** règle du dépôt. En
    écrire une seconde ici a déjà été un défaut, corrigé le 2026-08-29 : la bible est par
    PROJET, et sur le corpus réel 7 des 10 références vivent dans un autre tome que celui
    qu'on illustre."""
    entree = bible_mod.entree(bible_doc, nom)
    if entree is None:
        return []
    classes = classes_du_projet(racine_projet)
    sorties: list[Reference] = []
    for brute in entree.get("references") or []:
        if not isinstance(brute, dict):
            continue
        if str(brute.get("role") or "identite") != "identite":
            continue
        fichier = str(brute.get("fichier") or "")
        source = resoudre(fichier, racine_projet)
        if source is None:
            continue
        sorties.append(Reference(
            fichier=fichier, source=source,
            confiance=str(brute.get("confiance") or "proposee"),
            contexte=str(brute.get("contexte") or ""),
            cadre=_cadre(bible_mod.cadre_de(brute)),
            classe=classes.get(_cle_fichier(source), "")))
    return sorties


def _cle_fichier(source: Path) -> tuple:
    """`(tome, nom de fichier)` — deux tomes peuvent porter le même nom dans leur `media/`."""
    return (source.parent.parent.name, source.name)


#: Cache par racine de projet : `inventaire` relit chaque image du tome, et `references_de`
#: est appelée une fois par personnage.
_CLASSES: dict = {}


def classes_du_projet(racine_projet) -> dict:
    """`{(tome, fichier): classe}` pour tous les tomes du projet, avec la classification de
    `core/illustrations.py` — **la même** que celle du lot 23, pas une seconde.

    ⚠ L'inventaire est fait **sans mesure de couleur** (`avec_couleurs=False`) : le classement
    n'en a plus besoin depuis que le lot 23 a retiré le critère des « moins de 3 couleurs
    dominantes », et lire les pixels de tout un tome pour situer trois références serait
    payer cent fois le prix du résultat."""
    from core import illustrations as illus_mod

    racine = Path(racine_projet)
    cle = str(racine.resolve()) if racine.exists() else str(racine)
    if cle in _CLASSES:
        return _CLASSES[cle]
    table: dict = {}
    if racine.is_dir():
        for tome in sorted(p for p in racine.iterdir() if p.is_dir()):
            for illus in illus_mod.inventaire_rattache(tome, avec_couleurs=False):
                table[(tome.name, illus.nom)] = illus.classe
    _CLASSES[cle] = table
    return table


def _cadre(brut) -> tuple:
    """`[x, y, l, h]` en fractions, validé. Toute autre forme rend `()` — la page entière.

    ⚠ Un cadre à moitié valide est traité comme absent plutôt que corrigé : un recadrage
    silencieusement rectifié désignerait une autre partie de l'image que celle qu'un humain a
    validée. ⚠ **Et il est désormais SIGNALÉ** par `core/bible.py:_verifier_reference` : jusqu'au
    lot 29 la référence retombait sur la page entière sans que rien ne le dise.

    ⚠ Le champ se lit sous **deux noms** — `cadre` et l'alias historique `recadrage` — et la
    résolution passe par `core.bible.cadre_de`, jamais par une seconde règle écrite ici. Cf.
    `core.bible.CADRE_HERITE` : les deux noms ont coexisté six lots durant, et celui qui était
    écrit n'était pas celui qui était lu."""
    if not isinstance(brut, (list, tuple)) or len(brut) != 4:
        return ()
    try:
        valeurs = tuple(float(v) for v in brut)
    except (TypeError, ValueError):
        return ()
    x, y, largeur, hauteur = valeurs
    if largeur <= 0 or hauteur <= 0:
        return ()
    if not (0.0 <= x < 1.0 and 0.0 <= y < 1.0 and x + largeur <= 1.0001
            and y + hauteur <= 1.0001):
        return ()
    return valeurs


def resoudre(fichier: str, racine_projet) -> Path | None:
    """Le chemin réel d'une référence, ou `None`. Même règle que `bible.reference_existe`."""
    racine = Path(racine_projet)
    if not fichier or not racine.is_dir():
        return None
    relatif = Path(fichier)
    if (racine / relatif).is_file():
        return racine / relatif
    for tome in sorted(racine.iterdir()):
        if tome.is_dir() and (tome / relatif).is_file():
            return tome / relatif
    return None


def retenir(references: list[Reference], nombre: int) -> list[Reference]:
    """Les `nombre` références **validées par un humain** à retenir, **couvertures en dernier**.

    L'ordre est sinon celui de la bible, et il est stable : c'est ce qui rend deux exécutions
    du balayage comparables.

    ⚠ **Le rejet des couvertures en queue n'est PAS un tri par « meilleure » référence** — le
    banc ne saurait pas dire laquelle est la meilleure, et c'est précisément la question qu'il
    pose. C'est un fait que le dépôt connaît déjà : `core/illustrations.py` **classe** les
    couvertures, et dit d'elles qu'elles portent « un logo d'éditeur et un bandeau de prix ».

    ⚠ **Mesuré le 2026-08-29, et c'est ce qui a motivé cette ligne** : sur le corpus réel, les
    trois premières références validées de `Tory Noelle` sont **trois couvertures de light
    novel**, titre, nom d'auteur et numéro de tome compris — dont **deux sont le même dessin**
    (cosinus 0,9637). Les prendre dans l'ordre du fichier donnait au modèle d'édition trois
    fois la même composition typographiée. Elles restent utilisables — un personnage dont la
    couverture est la seule référence n'a pas d'autre choix — mais elles passent après."""
    validees = [r for r in references if r.validee]
    ordonnees = sorted(validees, key=lambda r: r.couverture)   # False < True : couverture après
    return ordonnees[:max(0, min(int(nombre), REFERENCES_MAX))]


def preparer(reference: Reference, destination, *, cote: int = COTE_REFERENCE) -> Path:
    """Écrit la référence recadrée et redimensionnée dans le dossier de la brique.

    ⚠ **L'original de `media/` n'est jamais ouvert en écriture** : on lit, on écrit ailleurs.
    Le périmètre de `illustration/frontiere.py` le vérifie à l'exécution, pas seulement ici.

    Le fichier écrit est un PNG **sans marquage** et c'est voulu : ce n'est pas une image
    générée, c'est un extrait de l'œuvre. Y écrire `AIGenerated=true` serait un mensonge —
    c'est pourquoi il passe par `frontiere.ecriture_extrait`, une porte plus étroite que
    `ecriture_marquee` : elle n'autorise **qu'un** chemin, et seulement dans le sous-dossier
    `references/`. Une image générée s'écrit à la racine du dossier de la brique et ne peut
    donc pas emprunter cette porte. Le tout vit sous `build/`, que `.gitignore` exclut déjà."""
    from PIL import Image

    from illustration import frontiere

    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    with Image.open(reference.source) as brute:
        image = brute.convert("RGB")
        if reference.cadre:
            largeur, hauteur = image.size
            x, y, cl, ch = reference.cadre
            image = image.crop((int(x * largeur), int(y * hauteur),
                                max(1, int((x + cl) * largeur)),
                                max(1, int((y + ch) * hauteur))))
        image.thumbnail((cote, cote), Image.LANCZOS)
        with frontiere.ecriture_extrait(destination) as cible:
            image.save(cible, format="PNG")
    return destination


def nom_prepare(personnage: str, index: int, reference: Reference) -> str:
    """`<ardoise>-ref1.png`. Le nom du PERSONNAGE, jamais celui de l'œuvre — même arbitrage
    que `illustration/requete.py:_ardoise`."""
    from illustration.requete import _ardoise
    return f"{_ardoise(personnage)}-ref{index}.png"


def preparer_toutes(references: list[Reference], personnage: str, dossier,
                    *, cote: int = COTE_REFERENCE) -> list[Path]:
    """Prépare chaque référence retenue. Rend les chemins écrits, dans l'ordre."""
    dossier = Path(dossier) / DOSSIER_REFERENCES
    return [preparer(r, dossier / nom_prepare(personnage, i, r), cote=cote)
            for i, r in enumerate(references, start=1)]


# ────────────────────────  Le prompt, quand des références l'accompagnent  ────────────────────────

def prompt_avec_references(prompt: str, nombre: int) -> str:
    """Ajoute la désignation en prose des images de référence.

    Le modèle d'édition ne reçoit pas les références comme des tenseurs anonymes : il faut les
    **nommer dans le texte**, exactement comme la carte de `Qwen-Image-Edit-2511` le décrit
    (« la personne de l'image 2 »). Une référence branchée mais jamais citée est une référence
    à moitié utilisée, et rien ne le signalerait."""
    if nombre <= 0:
        return prompt
    if nombre == 1:
        designation = ("Le personnage est celui de l'image 1 : garde son visage, sa coiffure "
                       "et sa tenue.")
    else:
        images = ", ".join(f"l'image {i}" for i in range(1, nombre + 1))
        designation = (f"Le personnage est celui montré dans {images} : garde son visage, sa "
                       f"coiffure et sa tenue, cohérents entre ces images.")
    return f"{prompt.rstrip()} {designation}".strip()


# ──────────────────────────  L25.2 — le garde-fou de refus  ──────────────────────────

@dataclass
class Planchers:
    """Les seuils du garde-fou. **Ils viennent de l'étalonnage, jamais d'une intuition.**

    `None` = non étalonné, donc le contrôle correspondant ne se prononce pas. Un seuil par
    défaut inventé serait pire qu'un seuil absent : il rendrait un verdict qui a l'air mesuré."""

    #: Sous ce cosinus moyen, l'image est marquée `ressemblance: faible`. C'est le plancher
    #: de CONFUSION de l'étape 0.2 — sous lui, l'image ne ressemble pas plus au personnage
    #: que deux personnages différents de la même œuvre ne se ressemblent.
    confusion: float | None = None
    #: Sous cette nouveauté, l'image est REJETÉE. Vient de l'étalonnage : c'est ce que valent
    #: deux images DISTINCTES du même personnage. Au-delà, l'image est plus proche de sa
    #: référence que deux pages réelles ne le sont l'une de l'autre — donc une reproduction.
    nouveaute: float | None = None
    #: Au-delà de cet écart moyen de descripteurs, l'image est marquée `style: hors_registre`.
    style_descripteurs: float | None = None
    #: Le juge sépare-t-il ? Vient de `juge.juge_utilisable`. Faux → les verdicts d'identité
    #: sont posés mais **signalés comme non opposables**.
    juge_utilisable: bool = False

    def resume(self) -> dict:
        return {"confusion": self.confusion, "nouveaute": self.nouveaute,
                "style_descripteurs": self.style_descripteurs,
                "juge_utilisable": self.juge_utilisable}


@dataclass
class Verdict:
    """Ce que le garde-fou dit d'une image produite. Les motifs sont nommés et comptés."""

    motifs: list = field(default_factory=list)
    marques: dict = field(default_factory=dict)
    rejetee: bool = False
    #: Le libellé du descripteur qui décroche, quand il y en a un.
    detail_style: str = ""

    def ajouter(self, motif: str, detail: str = "") -> None:
        self.motifs.append(motif)
        if detail:
            self.detail_style = detail

    def resume(self) -> dict:
        return {"motifs": list(self.motifs), "marques": dict(self.marques),
                "rejetee": self.rejetee, "detail_style": self.detail_style}


def exiger_references(references: list[Reference], personnage: str) -> list[Reference]:
    """Lève `SansReferenceValidee` s'il n'y a **aucune** référence validée par un humain.

    C'est le critère 5 du plan, et il n'a pas de nuance : « un personnage sans référence
    validée ne produit AUCUNE image »."""
    validees = [r for r in references if r.validee]
    if validees:
        return validees
    total = len(references)
    raise SansReferenceValidee(
        f"« {personnage} » : {MOTIFS_LISIBLES['sans_reference_validee']}.\n"
        f"  {total} référence(s) trouvée(s) dans la bible, {total} non validée(s) — il faut "
        f"`confiance: humaine`, posée par `python tools/bible.py --revue`.\n"
        f"  Aucune image n'est produite, et il n'y a pas de mode « au mieux » : générer un "
        f"portrait depuis une image que personne n'a regardée ferait passer une invention "
        f"pour une illustration de l'œuvre.")


def juger(grandeurs, planchers: Planchers) -> Verdict:
    """Le verdict d'une image, depuis ses trois grandeurs et les planchers étalonnés.

    ⚠ **Trois contrôles, trois effets DIFFÉRENTS**, et c'est le point : la nouveauté rejette,
    la ressemblance marque, le style marque. Les confondre — tout rejeter, ou tout signaler —
    perdrait ce que le plan demande de distinguer."""
    verdict = Verdict()

    if grandeurs is None:
        verdict.ajouter("juge_indisponible")
        verdict.marques["juge"] = "indisponible"
        return verdict

    if (planchers.nouveaute is not None and grandeurs.nouveaute is not None
            and grandeurs.nouveaute < planchers.nouveaute):
        verdict.ajouter("nouveaute_insuffisante")
        verdict.rejetee = True

    if (planchers.confusion is not None and grandeurs.ressemblance is not None
            and grandeurs.ressemblance < planchers.confusion):
        verdict.ajouter("ressemblance_faible")
        verdict.marques["ressemblance"] = "faible"

    if (planchers.style_descripteurs is not None
            and grandeurs.style_descripteurs is not None
            and grandeurs.style_descripteurs > planchers.style_descripteurs):
        nom, ecart = grandeurs.descripteur_decroche
        verdict.ajouter("style_hors_registre", detail=f"{nom} s'écarte de {ecart:.4f}")
        verdict.marques["style"] = "hors_registre"

    if not planchers.juge_utilisable and verdict.motifs:
        # ⚠ Le verdict est POSÉ quand même, et signalé comme non opposable. L'effacer
        # laisserait croire que rien n'a été mesuré ; le présenter comme un fait laisserait
        # croire que le juge sépare. Ni l'un ni l'autre.
        verdict.ajouter("juge_inutilisable")
        verdict.marques["juge"] = "non_opposable"

    return verdict


def compter_motifs(verdicts) -> dict:
    """`{motif: nombre}`, trié par nombre décroissant puis par nom — le format que le rapport
    du dépôt attend depuis `manga/detection_retry.py`."""
    compte: dict[str, int] = {}
    for verdict in verdicts:
        for motif in verdict.motifs:
            compte[motif] = compte.get(motif, 0) + 1
    return dict(sorted(compte.items(), key=lambda c: (-c[1], c[0])))
