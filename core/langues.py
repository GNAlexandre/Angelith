# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Alexandre Tournel

"""Packs de langue CIBLE — tout ce qui dépend de la langue dans laquelle on traduit.

## Pourquoi ce module

Le projet acceptait cinq langues **sources** et ne produisait que du **français**. Pas par
choix d'architecture : la langue de sortie n'était écrite nulle part en particulier, elle
était partout — dans les huit prompts, dans le guide de style, dans les gabarits `docx`/`css`,
et — c'est ce que l'inventaire a révélé — dans six consignes construites **en dur en Python**
(cf. `docs/mesures/inventaire-couplage-fr.md`, §5).

Un pack rassemble ces éléments en UN dossier. La conséquence qui compte n'est pas technique :
ajouter l'allemand devient un dossier de données à contribuer, sans toucher au moteur.

## Ce qu'un pack contient

    langues/<code>/
        pack.yaml          métadonnées, typographie, consignes
        prompts/*.md       les huit prompts
        style_guide.md
        templates/         reference.docx, epub.css

## Le repli de compatibilité, et sa date de péremption

⚠ Une config **sans** `langues.cible`, sur un dépôt **sans** `langues/`, doit se comporter
EXACTEMENT comme avant : mêmes fichiers lus, même sortie au bit près, aucun cache invalidé.
C'est ce qui fait de cette refonte un MINEUR et non un MAJEUR au sens du CHANGELOG.

Le mode compatibilité rend donc un pack SANS racine : `prompt()` sert `chemins.prompts`, et
`fichier()` rend `None` — chaque brique retombe alors sur le chemin qu'elle lisait déjà.
**Ce repli est temporaire et disparaît en 3.0.0**, quand `langues/fr/` sera le seul chemin. Il
n'est pas marqué par un `TODO` : le dépôt n'en contient aucun, et consigner une intention dans
une docstring est la façon dont il procède.

⚠ Le socle ne connaît QUE `chemins.prompts`. `chemins.style_guide`, `rendu.reference_docx` et
`rendu.epub_css` sont des artefacts du light novel : les lire ici ferait entrer la connaissance
d'une brique dans `core/`, ce que `tests/test_core_cli.py` interdit explicitement. Cf.
`Pack.fichier`.

## Ce qu'on ne fait PAS

**Aucun repli silencieux vers le français.** Un pack demandé mais introuvable, ou incomplet,
arrête le run *au démarrage* avec un message qui nomme ce qui manque. Six heures de GPU pour
découvrir qu'un tome est sorti dans la mauvaise langue coûtent infiniment plus cher qu'un
refus immédiat.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from .glossary_lang import NOMS

#: Langue de sortie par défaut. C'est la seule valeur pour laquelle le repli de
#: compatibilité s'applique : historiquement, le projet ne produisait que du français.
DEFAUT_CIBLE = "fr"

#: Racine des packs, relative au dossier de travail.
DEFAUT_PACKS = "langues"

#: Prompts qu'un pack DOIT fournir. Les cinq du light novel (`core.agents.NOMS_LN`) et les
#: trois du manga. La liste est écrite ici plutôt que dérivée des deux briques : un pack se
#: valide au démarrage, avant qu'on sache laquelle des deux va tourner.
PROMPTS_REQUIS = (
    "terminologue", "traducteur", "correcteur", "mise_en_page", "glossariste",
    "manga_traducteur", "manga_contexte", "manga_onomatopees",
)

#: Clés de consigne qu'un pack peut surcharger (cf. l'inventaire, §5). Déclarées ici pour que
#: `pack.yaml` puisse être validé et que `langues/README.md` ait une liste de référence — le
#: TEXTE, lui, n'est pas ici (voir `Pack.consigne`).
#:
#: ⚠ Les vingt-sept dernières sont celles du chemin MANGA (lot 15, L7.12). Le socle n'en
#: connaît que les NOMS : leur texte français vit dans `manga/consignes.py` et dans
#: `manga/relecture.py`, à leur site d'appel. C'est la même règle que `traduction_unitaire` :
#: une seule source par fragment, du côté qui l'emploie. Le socle, lui, doit pouvoir valider
#: un `pack.yaml` avant de savoir laquelle des deux briques va tourner, exactement comme pour
#: `PROMPTS_REQUIS`.
CONSIGNES_CONNUES = (
    "naturalisation_minimale", "naturalisation_legere", "naturalisation_moderee",
    "naturalisation_marquee", "titre_chapitre", "romanisation_rendu", "traduction_unitaire",
    "traduction_unitaire_place", "traduction_unitaire_replique",
    "manga_gabarit_ligne", "manga_gabarits_entete", "manga_separateur_planche",
    "manga_lot_consigne", "manga_precedentes_entete", "manga_precedente_ligne",
    "manga_bulles_entete", "manga_echantillon_entete", "manga_hors_bulle_entete",
    "manga_sfx_lecture_entete",
    "manga_ordre_droite_gauche", "manga_ordre_gauche_droite",
    "manga_groupe_entete", "manga_structure_note", "manga_image_planche",
    "manga_image_zone", "manga_crops_entete", "manga_origine_planche",
    "manga_type_pensee", "manga_type_recitatif", "manga_type_cri",
    "manga_relecteur", "manga_relecteur_manques", "manga_relecteur_manque_ligne",
    "manga_relecteur_source", "manga_relecteur_rendu",
    # Lot 27 — la légende obligatoire sous une illustration générée insérée dans un tome.
    # ⚠ Ce n'est pas une consigne envoyée à un modèle : c'est un texte que LE LECTEUR verra,
    # et il doit donc être dans la langue du tome. Son défaut français vit à son site
    # d'appel, `core/insertion.py:LEGENDE_FR`, comme toutes les autres.
    "legende_illustration_ia",
)


class ErreurPack(SystemExit):
    """Pack introuvable ou incomplet. `SystemExit` et non `Exception` : c'est une erreur de
    configuration, elle doit arrêter le programme avec son message, pas remonter une trace.

    Même convention que `LLM._effort`, qui est le précédent du dépôt pour une valeur de config
    invalide."""


@dataclass(frozen=True)
class Pack:
    """Un pack résolu. Immuable : il est lu une fois au démarrage et partagé partout."""

    code: str
    #: Racine du pack, ou `None` en mode compatibilité (anciens emplacements).
    racine: Path | None
    #: Dossier des prompts en mode compatibilité (`chemins.prompts`). Cette clé-là est
    #: partagée par les deux briques, elle a donc sa place dans le socle — contrairement à
    #: `rendu.reference_docx` ou `chemins.style_guide`, cf. `fichier()`.
    prompts_replis: Path = Path("prompts")
    typographie: dict = field(default_factory=dict)
    styles_word: dict = field(default_factory=dict)
    classes_css: dict = field(default_factory=dict)
    consignes: dict[str, str] = field(default_factory=dict)
    #: Nom de l'implémentation d'accord grammatical (`francais`, `aucun`). Cf. `accorder()`.
    accord: str = ""
    _nom: str = ""

    # ------------------------------------------------------------------ #
    # Nom de la langue
    # ------------------------------------------------------------------ #

    def nom_lisible(self) -> str:
        """Nom de la langue tel qu'on l'écrit à un modèle : « français », « anglais ».

        ⚠ Un nom, jamais un code. La docstring de `glossary_lang.NOMS` porte la raison : un
        prompt qui dit « bulles en anglais » fait un travail que « bulles en [en] » ne fait
        pas — les modèles raisonnent sur des noms de langue, pas sur des codes ISO."""
        return self._nom or NOMS.get(self.code) or self.code

    # ------------------------------------------------------------------ #
    # Fichiers
    # ------------------------------------------------------------------ #

    def prompt(self, nom: str) -> Path:
        """Chemin du prompt système d'un agent.

        Le seul fichier dont le socle connaisse l'emplacement, parce que `chemins.prompts` est
        la seule clé de cette famille que les DEUX briques partagent (cf. `fichier`)."""
        if self.racine is not None:
            return self.racine / "prompts" / f"{nom}.md"
        return self.prompts_replis / f"{nom}.md"

    def fichier(self, relatif: str) -> Path | None:
        """Un fichier du pack s'il existe, `None` sinon. **L'appelant fournit son repli.**

        ⚠ C'est une règle de couche, pas un détail de signature. `style_guide.md`,
        `templates/reference.docx` et `templates/epub.css` sont des artefacts du light novel :
        leurs clés de config (`chemins.style_guide`, `rendu.reference_docx`, `rendu.epub_css`)
        n'ont rien à faire dans `core/`, et `tests/test_core_cli.py` le vérifie explicitement —
        « le mettre dans `core/` y ferait entrer la connaissance d'une brique ».

        Le socle sait donc servir *un fichier d'un pack*, et rien de plus. La brique décide de
        ce qu'elle demande et de ce qu'elle fait quand le pack ne le fournit pas :

            chemin = pack.fichier("style_guide.md") or Path(config["chemins"]["style_guide"])

        Ce repli est délibérément TOLÉRANT, contrairement aux prompts : un `reference.docx` est
        déjà un réglage que l'utilisateur personnalise, et un pack qui n'en fournit pas n'est
        pas cassé — c'est un pack qui laisse ce choix. Un prompt manquant, lui, produirait un
        tome dans la mauvaise langue, et `_verifier_prompts` le refuse."""
        if self.racine is None:
            return None
        chemin = self.racine / relatif
        return chemin if chemin.exists() else None

    def accorder(self):
        """Règles d'accord grammatical de cette langue, pour le forçage déterministe.

        Le français accorde le déterminant, répare les élisions (`l'` → `le`/`la`) et refuse
        un remplacement dont le genre est incertain ; l'anglais n'a rien à accorder ;
        l'allemand aurait besoin des cas.

        ⚠ **« Ne rien faire » est une réponse complète, pas une implémentation en attente.**
        Pour l'anglais, le forçage se réduit à la substitution — c'est exactement ce qu'il doit
        être. Le défaut reste le français : sans pack, le comportement ne change pas.

        Le principe à préserver quelle que soit l'implémentation : le déterministe ne doit
        JAMAIS introduire une faute que le modèle n'aurait pas faite."""
        from .glossary_force import accord_pour
        return accord_pour(self.accord)

    # ------------------------------------------------------------------ #
    # Consignes
    # ------------------------------------------------------------------ #

    def consigne(self, cle: str, defaut: str) -> str:
        """Fragment de message dépendant de la langue cible, ou `defaut` si le pack n'en
        déclare pas (cf. `CONSIGNES_CONNUES` et l'inventaire, §5).

        ⚠ **`defaut` est le texte français, et il reste à son site d'appel.** Le recopier ici
        en ferait une seconde source : deux chaînes libres de diverger, dont l'une décide de
        la sortie d'un tome. En le laissant chez l'appelant, l'identité au bit près du mode
        compatibilité est vraie *par construction*, pas par vigilance.

        Ces fragments ne sont pas des prompts système, d'où leur absence de `prompts/` : ils
        sont injectés dans un MESSAGE, conditionnellement — la romanisation ne part que sur un
        pivot CJK, la naturalisation que selon `naturalisation.intensite`."""
        valeur = self.consignes.get(cle)
        return valeur if valeur else defaut


def _lire_pack_yaml(dossier: Path) -> dict:
    import yaml
    chemin = dossier / "pack.yaml"
    if not chemin.exists():
        raise ErreurPack(
            f"pack de langue « {dossier.name} » incomplet : {chemin} est absent.\n"
            f"  → un pack doit porter un pack.yaml (code, nom, typographie). "
            f"Voir langues/README.md.")
    try:
        return yaml.safe_load(chemin.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError as err:
        raise ErreurPack(f"pack de langue « {dossier.name} » : {chemin} est illisible.\n"
                         f"  → {err}") from None


def _verifier_prompts(dossier: Path) -> None:
    """Refuse un pack auquel il manque un prompt.

    ⚠ C'est ici que se joue la règle « aucun repli silencieux ». Servir le prompt français
    d'un agent absent produirait un tome dont, disons, les onomatopées seraient françaises et
    le reste anglais — six heures de GPU pour un résultat inutilisable, et rien dans le
    journal pour dire pourquoi."""
    manquants = [n for n in PROMPTS_REQUIS if not (dossier / "prompts" / f"{n}.md").exists()]
    if manquants:
        raise ErreurPack(
            f"pack de langue « {dossier.name} » incomplet : "
            f"{len(manquants)} prompt(s) absent(s) sous {dossier / 'prompts'}.\n"
            + "".join(f"  → {n}.md\n" for n in manquants)
            + "  Un prompt manquant produirait un tome partiellement dans une autre langue : "
              "on refuse plutôt que de replier en silence.")


def _packs_disponibles(racine: Path) -> list[str]:
    if not racine.is_dir():
        return []
    return sorted(d.name for d in racine.iterdir() if (d / "pack.yaml").exists())


def _dossier_prompts(config: dict) -> Path:
    """`chemins.prompts`, la seule clé de chemin que les deux briques partagent.

    `manga/agents_manga.py` le dit dans sa docstring : les prompts manga sont cherchés dans le
    MÊME dossier que ceux du light novel. Elle a donc sa place dans le socle, là où
    `chemins.style_guide` et `rendu.*` ne l'ont pas."""
    from .installation import donnee_livree
    valeur = (config.get("chemins") or {}).get("prompts")
    return donnee_livree(str(valeur) if valeur else "prompts")


def _pack_de_compatibilite(config: dict) -> Pack:
    """Le comportement d'avant la refonte, servi par la même interface.

    ⚠ Aucune donnée nouvelle ici : les chemins viennent de `chemins.*` et `rendu.*` tels
    qu'ils étaient lus avant, et les consignes sont le texte français verbatim. C'est ce qui
    garantit qu'une config inchangée rend une sortie identique au bit près."""
    return Pack(code=DEFAUT_CIBLE, racine=None, prompts_replis=_dossier_prompts(config),
                _nom=NOMS.get(DEFAUT_CIBLE, "français"))


def _pack_de_dossier(dossier: Path, code: str, config: dict) -> Pack:
    meta = _lire_pack_yaml(dossier)
    _verifier_prompts(dossier)
    return Pack(
        code=str(meta.get("code") or code),
        racine=dossier,
        prompts_replis=_dossier_prompts(config),
        typographie=dict(meta.get("typographie") or {}),
        styles_word=dict(meta.get("styles_word") or {}),
        classes_css=dict(meta.get("classes_css") or {}),
        # ⚠ Les valeurs VIDES sont écartées ici, pas dans `consigne()` : une clé laissée
        # vide dans le YAML donne `None`, et `str(None)` rend « None » — une consigne
        # littérale « None » envoyée au modèle, ce qui est pire que le français.
        accord=str(meta.get("accord") or ""),
        consignes={k: str(v) for k, v in (meta.get("consignes") or {}).items()
                   if v is not None and str(v).strip()},
        _nom=str(meta.get("nom") or NOMS.get(code) or code),
    )


def resoudre_pack(config: dict) -> Pack:
    """Le pack de langue cible du run. À appeler UNE fois, au démarrage.

    Trois cas, dans cet ordre :

    1. `langues/<cible>/` existe → on le sert, après vérification qu'il est complet ;
    2. aucun dossier `langues/` **et** cible par défaut → mode compatibilité (§ en-tête) ;
    3. tout le reste → `ErreurPack`, avec la liste des packs réellement disponibles.

    Le cas 3 couvre la faute de frappe (`cible: fp`) comme le pack jamais installé. Dans les
    deux cas le message nomme ce qui existe : « introuvable » sans la liste oblige à aller
    lister le dossier soi-même."""
    from .installation import donnee_livree
    langues = config.get("langues") or {}
    cible = str(langues.get("cible") or DEFAUT_CIBLE).strip().lower()
    # ⚠ `donnee_livree` et non `Path` depuis la 2.31.0 (`PLAN-37` L37.3) : dans un gel, les
    # prompts sont dépaquetés sous `sys._MEIPASS` et `Path("langues")` désignerait le dossier
    # d'où le raccourci a été lancé. L'ordre ne peut rien casser — ce que le répertoire courant
    # offre gagne, le paquet n'est qu'un repli.
    racine = donnee_livree(str(langues.get("packs") or DEFAUT_PACKS))
    dossier = racine / cible

    if dossier.is_dir():
        return _pack_de_dossier(dossier, cible, config)

    if not racine.exists() and cible == DEFAUT_CIBLE:
        return _pack_de_compatibilite(config)

    disponibles = _packs_disponibles(racine)
    detail = (", ".join(disponibles) if disponibles
              else f"aucun — {racine} est vide ou absent")
    # Même geste que `core.config._suggestion` pour une clé mal orthographiée : nommer le
    # coupable probable vaut mieux que dire « introuvable ». `cible: fp` est une faute de
    # frappe bien plus probable qu'une demande de pack finnois.
    import difflib
    # ⚠ Seuil à 0,5 et non 0,6 : un code de langue fait DEUX caractères, donc une faute
    # d'une seule lettre (`fp` pour `fr`) donne exactement 0,5. À 0,6, la suggestion ne se
    # déclenchait jamais sur le cas qu'elle vise.
    proche = difflib.get_close_matches(cible, disponibles, n=1, cutoff=0.5)
    indice = f"\n  → vouliez-vous dire « {proche[0]} » ?" if proche else ""
    raise ErreurPack(
        f"pack de langue « {cible} » introuvable dans {racine}/.\n"
        f"  → packs disponibles : {detail}{indice}\n"
        f"  → corrige `langues.cible` dans config.yaml, ou ajoute le pack "
        f"(voir langues/README.md).")
