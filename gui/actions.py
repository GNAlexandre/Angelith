# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Alexandre Tournel

"""Catalogue des actions de la fenêtre — **déclaré ici, en Python nu**.

## Pourquoi une table, et pas des `QAction` posées à la main

Parce que la règle du lot 18 est vérifiable ou elle n'est rien : « toute action de l'interface
est atteignable par un menu, et le menu affiche son raccourci ». Une règle qui ne s'énonce
qu'en prose se perd au troisième ajout de bouton.

La table ci-dessous est la source unique. `gui/fenetre.py` la parcourt pour construire la barre
de menus, et `tests/test_gui_actions.py` la parcourt pour vérifier :

- qu'aucune séquence de touches n'est déclarée deux fois — c'est le test qui aurait attrapé le
  `Ctrl+Shift+S` posé à la fois sur le bouton « Enregistrer les modifications du projet » et
  sur son entrée de menu, deux raccourcis de portée fenêtre pour un seul geste ;
- que chaque identifiant a bien une méthode qui le sert dans la fenêtre.

Aucun import Qt ici : `QKeySequence` sait normaliser « Ctrl+Shift+S », mais s'en remettre à lui
rendrait le test dépendant de PySide6 — or ce test doit tourner dans le job qui ne l'installe
pas. La normalisation faite ici est celle dont le catalogue a besoin, et rien de plus : casse
et ordre des modificateurs.

## Ce que la table ne décide pas

Elle ne dit pas ce qu'une action FAIT. Elle nomme un identifiant ; la fenêtre le relie à une
méthode. C'est ce qui permet de tester la table sans construire une fenêtre, et la fenêtre
sans recopier la table.
"""
from __future__ import annotations

from dataclasses import dataclass

#: Ordre des menus dans la barre — celui du plan, et il suit l'usage général
#: (Fichier · Édition · Affichage · <navigation> · <métier> · Aide).
#:
#: ⚠ « Aller à » est né avec le lot 31. Une nav latérale sans entrées de menu serait un
#: raccourci que rien n'apprend : « un menu n'est pas un rangement, c'est un index
#: découvrable — c'est aussi le seul endroit où un utilisateur apprend qu'un raccourci
#: existe ». Les sept destinations y sont, avec leur séquence.
MENUS: tuple[str, ...] = ("Fichier", "Édition", "Affichage", "Aller à", "Projet", "Aide")

#: Marque de séparateur dans la liste d'entrées d'un menu.
SEPARATEUR = "—"

#: Ordre canonique des modificateurs, pour comparer deux écritures d'un même raccourci.
#: `Shift+Ctrl+S` et `Ctrl+Shift+S` sont la MÊME séquence pour Qt ; les laisser passer pour
#: deux entrées distinctes ferait mentir le test d'unicité, qui est tout l'intérêt de la table.
_ORDRE_MODIFICATEURS = ("ctrl", "alt", "shift", "meta")


@dataclass(frozen=True)
class Action:
    """Une entrée de menu.

    `identifiant` — le nom que `gui/fenetre.py` relie à une méthode `action_<identifiant>`.
    `raccourci` — `None` quand l'action n'en a pas ; jamais deux fois la même valeur.
    `alias` — raccourcis supplémentaires acceptés mais NON affichés dans le menu. C'est le
    repli de `F` (cf. `PLAN-18` L18.4) : un raccourci mono-touche dans un panneau qui porte
    deux champs de saisie est une bombe à retardement, mais le retirer casserait la main de
    qui l'utilise depuis six mois.
    `exige_tome` — grisée tant qu'aucun tome n'est ouvert.
    `bascule` — l'action est une case à cocher (menu « Affichage »).
    `groupe` — titre d'un SOUS-menu. Les entrées consécutives qui portent le même groupe y
    sont rassemblées ; six filtres de pellicule à la racine du menu « Affichage » le
    noieraient sous ce qui n'est qu'un réglage de tri.
    `methode` — nom du gestionnaire quand il est partagé par plusieurs entrées (les six
    filtres appellent tous `action_filtre`, avec `donnee` pour les distinguer). Vide = le
    gestionnaire porte le nom de l'identifiant.
    `donnee` — la charge passée au gestionnaire partagé.
    """

    identifiant: str
    menu: str
    libelle: str
    raccourci: str | None = None
    infobulle: str = ""
    exige_tome: bool = False
    bascule: bool = False
    alias: tuple[str, ...] = ()
    groupe: str = ""
    methode: str = ""
    donnee: object = None

    @property
    def gestionnaire(self) -> str:
        """Le nom de la méthode de `Fenetre` qui sert cette entrée."""
        return f"action_{self.methode or self.identifiant}"


def normaliser(sequence: str) -> str:
    """`« shift+ctrl+s »` → `« Ctrl+Shift+S »`. Suffisant pour comparer deux déclarations.

    ⚠ Ne prétend PAS reproduire `QKeySequence` : les séquences à plusieurs accords
    (`Ctrl+K, Ctrl+S`) ne sont pas utilisées ici, et le jour où elles le seraient, ce sont
    elles qu'il faudrait apprendre à découper — le test d'unicité le dirait aussitôt, en les
    voyant toutes se réduire à la même chaîne."""
    brut = sequence.replace("++", "+plus")
    morceaux = [m.strip().lower() for m in brut.split("+") if m.strip()]
    modificateurs = [m for m in _ORDRE_MODIFICATEURS if m in morceaux]
    reste = [m for m in morceaux if m not in _ORDRE_MODIFICATEURS]
    lisibles = []
    for m in reste:
        lisibles.append("+" if m == "plus" else m.upper() if len(m) == 1 else m.capitalize())
    return "+".join([m.capitalize() for m in modificateurs] + lisibles)


#: Titre du sous-menu des filtres de pellicule.
GROUPE_FILTRES = "Filtre de la pellicule"

#: Titre du sous-menu des thèmes.
GROUPE_THEME = "Thème"

#: Libellés des trois modes de thème, DANS L'ORDRE du menu, et l'identifiant qui va avec.
#:
#: ⚠ Les valeurs (`auto`, `clair`, `sombre`) sont celles de `gui/theme.MODES` ; le test
#: `test_les_themes_du_menu_sont_ceux_du_theme` refuse qu'elles divergent. Un menu qui
#: proposerait un mode que le thème ne connaît pas donnerait un clic sans effet — exactement
#: le défaut que la table des actions existe pour empêcher.
THEMES: tuple[tuple[str, str], ...] = (
    ("auto", "Suivre le système"),
    ("clair", "Clair"),
    ("sombre", "Sombre"),
)


def _themes() -> tuple[Action, ...]:
    """Les trois modes de thème — des BASCULES exclusives, comme les filtres.

    Un menu qui dirait seulement « un thème existe » sans dire lequel est actif ne vaudrait pas
    la ligne qu'il occupe."""
    return tuple(
        Action(f"theme_{mode}", "Affichage", libelle, bascule=True, groupe=GROUPE_THEME,
               methode="theme", donnee=mode,
               infobulle="Le canevas reste sombre dans les deux thèmes : c'est la convention "
                         "des outils d'image, et elle vaut pour un fond de planche.")
        for mode, libelle in THEMES)


#: `identifiant de destination → séquence`. **La seule déclaration de ces raccourcis.**
#:
#: ⚠ `gui/destinations.py` porte le NOM de l'action (`aller_manga`), jamais la séquence : deux
#: catalogues de séquences seraient deux vérités, et le `Ctrl+Shift+S` posé deux fois au lot 18
#: venait exactement de là.
#:
#: `Ctrl+1` … `Ctrl+6` vont aux **six destinations métier**, dans l'ordre du pane. L'accueil
#: prend `Ctrl+Shift+A` plutôt que `Ctrl+1` pour deux raisons : le plan attribue nommément
#: `Ctrl+1`…`Ctrl+6` aux six, et `Ctrl+Début` — l'autre candidat — est déjà « aller au début du
#: document » dans les deux champs de saisie de la retouche, qu'un raccourci de portée fenêtre
#: lui volerait sans rien dire.
SEQUENCES_DESTINATIONS: dict[str, str] = {
    "accueil": "Ctrl+Shift+A",
    "light_novel": "Ctrl+1",
    "manga": "Ctrl+2",
    "webtoon": "Ctrl+3",
    "illustrations": "Ctrl+4",
    "oeuvres": "Ctrl+5",
    "retouche": "Ctrl+6",
}


def _destinations() -> tuple[Action, ...]:
    """Les entrées « Aller à », **dérivées de `gui/destinations.py`**.

    Dérivées, pas recopiées — même raison que pour les six filtres : deux listes qui
    divergeraient donneraient un menu proposant une destination que le pane ne connaît pas.

    Les entrées de PIED (Réglages, Diagnostic) n'apparaissent pas ici : elles déclenchent une
    action qui a déjà son entrée de menu ailleurs, et la lister deux fois donnerait deux
    libellés pour un seul geste."""
    from .destinations import corps
    return tuple(
        Action(f"aller_{d.identifiant}", "Aller à", d.libelle,
               SEQUENCES_DESTINATIONS.get(d.identifiant), infobulle=d.infobulle,
               methode="aller", donnee=d.identifiant)
        for d in corps())


def _filtres() -> tuple[Action, ...]:
    """Les six filtres de la pellicule, **dérivés de `gui/pellicule.FILTRES`**.

    ⚠ Dérivés, pas recopiés. La liste déroulante de l'éditeur lit la même table ; deux listes
    qui divergeraient donneraient un menu qui propose un filtre que le panneau ne connaît pas,
    et le clic ne ferait rien.

    Ce sont des BASCULES exclusives : le menu doit dire lequel est actif, sinon il rappelle
    seulement qu'un filtre existe — ce qu'on savait déjà en voyant la pellicule à moitié vide."""
    from .pellicule import FILTRES
    return tuple(
        Action(f"filtre_{n}", "Affichage", nom, bascule=True, exige_tome=True,
               groupe=GROUPE_FILTRES, methode="filtre", donnee=nom,
               infobulle="Ne montrer que ces planches. La planche affichée n'est jamais "
                         "masquée.")
        for n, nom in enumerate(FILTRES))


#: **La** table. Un ajout ici suffit à faire apparaître l'entrée dans le menu ; le test
#: d'unicité et le test de couverture des méthodes s'appliquent immédiatement.
CATALOGUE: tuple[Action | str, ...] = (
    # -- Fichier ------------------------------------------------------------------------ #
    Action("nouveau_projet", "Fichier", "Nouveau projet…",
           infobulle="Crée sources/<Projet>/<Tome>/<format>/ et y COPIE les images ou "
                     "l'archive choisies."),
    Action("ouvrir_sources", "Fichier", "Ouvrir le dossier de sources",
           infobulle="Ouvre sources/ dans l'explorateur de fichiers du système."),
    Action("tome_de_demonstration", "Fichier", "Créer un tome de démonstration",
           infobulle="Écrit un tome fabriqué par Angelith lui-même — aucune œuvre, "
                     "redistribuable sans réserve — pour essayer l'application sur une "
                     "installation neuve. Marqué comme démonstration, supprimable."),
    SEPARATEUR,
    Action("enregistrer_planche", "Fichier", "Enregistrer cette planche", "Ctrl+S",
           infobulle="Écrit sur le disque ce qui a été modifié sur la planche affichée.",
           exige_tome=True),
    Action("enregistrer_tome", "Fichier", "Enregistrer tout le tome", "Ctrl+Shift+S",
           infobulle="Écrit toutes les planches en attente, relettre celles dont le rendu "
                     "est périmé, puis réassemble le CBZ/PDF UNE seule fois.",
           exige_tome=True),
    SEPARATEUR,
    Action("ouvrir_build", "Fichier", "Ouvrir le dossier de build du tome", exige_tome=True),
    Action("ouvrir_config", "Fichier", "Réglages avancés (fichier)",
           infobulle="Ouvre config.yaml dans l'éditeur système. L'interface ne le réécrit "
                     "jamais : ses commentaires en sont la documentation."),
    SEPARATEUR,
    Action("quitter", "Fichier", "Quitter", "Ctrl+Q"),

    # -- Édition ------------------------------------------------------------------------ #
    Action("annuler", "Édition", "Annuler", "Ctrl+Z", exige_tome=True),
    Action("refaire", "Édition", "Refaire", "Ctrl+Y", exige_tome=True),
    SEPARATEUR,
    Action("rechercher", "Édition", "Rechercher dans le tome", "Ctrl+F", exige_tome=True,
           infobulle="Met le curseur dans le champ de recherche de la pellicule."),
    Action("remplacer", "Édition", "Remplacer dans le tome", "Ctrl+H", exige_tome=True,
           infobulle="Met le curseur dans le champ de remplacement. Le remplacement porte "
                     "sur toutes les occurrences cochées, dans TOUT le tome."),

    # -- Affichage ---------------------------------------------------------------------- #
    Action("zoom_plus", "Affichage", "Zoom avant", "Ctrl++", exige_tome=True),
    Action("zoom_moins", "Affichage", "Zoom arrière", "Ctrl+-", exige_tome=True),
    Action("ajuster", "Affichage", "Ajuster à la fenêtre", "Ctrl+0", alias=("F",),
           exige_tome=True,
           infobulle="Ramène la planche entière dans la fenêtre. « F » reste accepté."),
    Action("garder_cadrage", "Affichage", "Garder le cadrage d'une planche à l'autre",
           bascule=True, exige_tome=True),
    SEPARATEUR,
    Action("comparer_rendu", "Affichage", "Comparer au rendu du pipeline", bascule=True,
           exige_tome=True),
    SEPARATEUR,
    *_filtres(),
    SEPARATEUR,
    *_themes(),
    SEPARATEUR,
    Action("journal", "Affichage", "Journal", "Ctrl+J"),
    SEPARATEUR,
    Action("reinitialiser_disposition", "Affichage", "Réinitialiser la disposition",
           infobulle="Rend à la fenêtre sa taille et ses colonnes d'origine, et efface le "
                     "fichier de réglages de l'interface."),

    # -- Aller à ------------------------------------------------------------------------ #
    #
    # ⚠ `onglet_suivant` a disparu avec les onglets, et son raccourci est REPRIS ici plutôt
    # qu'abandonné : `Ctrl+Tab` fait la même promesse — « passe à la suivante » — sur sept
    # destinations au lieu de trois onglets. Le retirer casserait la main de qui l'utilise
    # sans rien apporter.
    *_destinations(),
    SEPARATEUR,
    Action("destination_suivante", "Aller à", "Destination suivante", "Ctrl+Tab",
           infobulle="Passe à la destination suivante du pane, en boucle. Les entrées de "
                     "pied (Réglages, Diagnostic) en sont exclues."),

    # -- Projet ------------------------------------------------------------------------- #
    Action("recharger_glossaire", "Projet", "Recharger le glossaire depuis le disque",
           exige_tome=True,
           infobulle="À faire après avoir édité glossaire.yaml à la main : le glossaire est "
                     "gardé en mémoire pour ne pas le relire à chaque bulle traduite."),
    Action("importer_glossaire", "Projet", "Importer un glossaire…",
           infobulle="Fusionne un glossaire rédigé à la main (.docx / .txt / .md) ou un "
                     "glossaire YAML antérieur dans sources/<Projet>/glossaire.yaml."),
    Action("importer_build", "Projet", "Importer un tome corrigé…", exige_tome=True,
           infobulle="Réintègre le travail d'un relecteur : répliques corrigées, zones "
                     "retouchées, textes déplacés. ⚠ Rien n'est supprimé, et ce qui est "
                     "remplacé est sauvegardé d'abord. Un aperçu dit ce qui va changer avant "
                     "d'écrire."),
    Action("optimiser_glossaire", "Projet", "Optimiser le glossaire…",
           infobulle="Dédoublonne le glossaire de l'œuvre — appels LLM, plusieurs minutes."),
    SEPARATEUR,
    Action("assembler", "Projet", "Assembler CBZ/PDF", exige_tome=True),
    SEPARATEUR,
    Action("preferences", "Projet", "Préférences…",
           infobulle="Réglages de l'INTERFACE seulement. config.yaml n'est jamais réécrit."),

    # -- Aide --------------------------------------------------------------------------- #
    Action("raccourcis", "Aide", "Raccourcis clavier", "F1"),
    Action("legende_symboles", "Aide", "Légende des symboles"),
    SEPARATEUR,
    Action("diagnostic", "Aide", "Diagnostic complet",
           infobulle="Ce qui manque à cette installation, ce que ça coûte, et quoi faire. "
                     "L'équivalent structuré de `run_manga.py --check` et `run.py --check`. "
                     "Depuis le lot 36 c'est une DESTINATION, pas un dialogue — d'où "
                     "l'absence de points de suspension."),
    Action("tester_llm", "Aide", "Tester la connexion LLM…"),
    SEPARATEUR,
    Action("rechercher_maj", "Aide", "Rechercher une mise à jour…",
           infobulle="Demande à GitHub s'il existe une version plus récente, et propose de "
                     "l'installer. L'installeur est vérifié par son empreinte SHA-256 — ce "
                     "qui détecte un téléchargement altéré, mais ne remplace PAS une "
                     "signature de code. Depuis les sources, ce bouton ouvre la page des "
                     "releases et n'installe rien."),
    Action("a_propos", "Aide", "À propos"),
)


def actions() -> tuple[Action, ...]:
    """Les entrées du catalogue, séparateurs exclus."""
    return tuple(e for e in CATALOGUE if isinstance(e, Action))


def par_menu(nom: str) -> tuple[Action | str, ...]:
    """Les entrées d'un menu, séparateurs COMPRIS et dans l'ordre.

    Les séparateurs de tête et de queue sont retirés : un menu qui commence ou finit par un
    trait est le signe d'une entrée supprimée, pas d'une intention."""
    dedans, sortie = False, []
    for entree in CATALOGUE:
        if isinstance(entree, Action):
            dedans = entree.menu == nom
            if dedans:
                sortie.append(entree)
        elif dedans:
            sortie.append(entree)
    while sortie and not isinstance(sortie[-1], Action):
        sortie.pop()
    return tuple(sortie)


def sequences() -> dict[str, list[str]]:
    """`{séquence normalisée: [identifiants qui la déclarent]}`, alias compris."""
    trouvees: dict[str, list[str]] = {}
    for action in actions():
        for brute in filter(None, (action.raccourci, *action.alias)):
            trouvees.setdefault(normaliser(brute), []).append(action.identifiant)
    return trouvees


def doublons() -> dict[str, list[str]]:
    """Les séquences déclarées par plus d'une action. Vide = la table est saine."""
    return {seq: ids for seq, ids in sequences().items() if len(ids) > 1}
