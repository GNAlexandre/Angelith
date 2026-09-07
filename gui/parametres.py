# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Alexandre Tournel

"""Catalogue des paramètres de run — **déclaré ici, en Python nu**.

## Pourquoi une troisième table, après `actions.py` et `destinations.py`

Les trois répondent à trois questions différentes. `actions.py` dit *ce que l'application
sait faire*, `destinations.py` dit *où l'on peut se trouver*, celle-ci dit *ce qu'on peut
régler avant de lancer*. Le patron, lui, est **exactement** le même : une table gelée, aucun
import Qt, et des tests qui la parcourent sans construire de fenêtre.

Ce que la table achète, et c'est le point du `PLAN-33` L33.1 :

1. **un seul générateur de formulaire** (`gui/formulaire.py`) pour les quatre destinations
   de lancement. Quatre formulaires écrits à la main divergeraient au troisième ajout — le
   lanceur en portait sept réglages utiles, la CLI manga en porte vingt-huit ;
2. **le test que le lot 18 avait dû écrire à la main** : chaque paramètre a un libellé qui
   dit l'EFFET, une infobulle qui porte l'équivalent en ligne de commande, et un défaut ;
   aucun identifiant n'est déclaré deux fois pour un même panneau ;
3. **le croisement avec l'inventaire des drapeaux** (`tools/inventaire_drapeaux.py`) : tout
   drapeau des quatre CLI est soit ici, soit dans `AILLEURS`, soit dans `NON_EXPOSES` **avec
   son motif**. Un drapeau ajouté demain à une CLI casse `tests/test_inventaire_drapeaux.py`.

## ⚠ `panneaux`, et non `briques`

Le `PLAN-33` esquissait `briques: ("manga", "webtoon")`. Le champ s'appelle `panneaux` et
porte des identifiants de **destination**, parce que le dépôt tient une distinction que ce
nom-là effacerait : **le webtoon n'est pas une brique**. `core/version.py:ETAT_BRIQUES` en
connaît quatre — `ln`, `manga`, `scan`, `illustration` — et le webtoon n'en fait pas partie :
c'est `--format webtoon` du même orchestrateur (`gui/destinations.py`, `gui/lanceur.py`).
Nommer « brique » une colonne qui contient `webtoon` aurait installé dans une table gelée
l'exacte confusion que le lot 31 a passé du temps à défaire.

## ⚠ La règle du défaut « selon `config.yaml` », généralisée

`defaut=None` veut dire **« ne pose pas la clé »**, et non « pose sa valeur par défaut ». La
règle était écrite pour un seul menu — celui de `--think`, dont la première entrée « ne vaut
pas `false` : elle ne pose pas la clé du tout », parce que poser `think: false` écraserait
aussi l'`endpoint:` de l'agent. Elle vaut ici pour **tous** les paramètres à trois états, et
`appliquer()` est le seul endroit qui décide où chaque valeur atterrit :
`tests/test_gui_parametres.py` vérifie qu'un formulaire laissé à ses défauts ne pose **aucune**
clé dans le dictionnaire de configuration.

## Ce que la table ne décide pas

Elle ne dit pas comment un paramètre s'affiche — c'est `gui/formulaire.py` — ni ce qu'il fait
au pipeline — c'est `appliquer()` juste en dessous, qui est la seule fonction du module à
connaître la forme de `config.yaml`. Cette séparation est ce qui permet de tester la table
sans Qt, et le générateur sans recopier la table.
"""
from __future__ import annotations

from dataclasses import dataclass, field

#: Les quatre panneaux qui construisent un formulaire depuis cette table. Ce sont des
#: identifiants de `gui/destinations.py`, pas des briques — cf. l'avertissement du module.
LIGHT_NOVEL = "light_novel"
MANGA = "manga"
WEBTOON = "webtoon"
ILLUSTRATIONS = "illustrations"

PANNEAUX: tuple[str, ...] = (LIGHT_NOVEL, MANGA, WEBTOON, ILLUSTRATIONS)

#: Les cinq genres de contrôle. Un genre de plus demande une branche dans le générateur : la
#: liste est courte **par construction**, et c'est ce qui garde le générateur lisible.
BASCULE = "bascule"      # QCheckBox
CHOIX = "choix"          # QComboBox, valeurs portées par `choix`
ENTIER = "entier"        # QSpinBox
REEL = "reel"            # QDoubleSpinBox
TEXTE = "texte"          # QLineEdit

GENRES: frozenset[str] = frozenset({BASCULE, CHOIX, ENTIER, REEL, TEXTE})

#: Les groupes de formulaire, **dans l'ordre d'affichage**. Un paramètre nomme son groupe ;
#: le générateur les rend dans cet ordre, et saute ceux qu'un panneau ne remplit pas.
GROUPES: tuple[tuple[str, str], ...] = (
    ("cible", "Ce qui va tourner"),
    ("lot", "Traduction par lots"),
    ("detection", "Détection"),
    ("bande", "Découpage de la bande (webtoon)"),
    ("image", "Ce qui va être dessiné"),
    ("modele", "Modèle"),
    ("nuit", "Run de nuit"),
)


@dataclass(frozen=True)
class Parametre:
    """Un réglage de run, tel que l'interface le pose et tel que la CLI le nomme.

    `identifiant` — la clé sous laquelle la valeur circule (réglages, profils, `appliquer`).
    `panneaux` — les destinations de lancement qui l'offrent.
    `libelle` — ce que lit l'utilisateur. **Il dit l'EFFET, jamais le drapeau** : une case
    nommée `--force` demande de connaître `run_manga.py` pour savoir ce qu'elle coûte.
    `genre` — l'un des cinq ci-dessus.
    `defaut` — la valeur de départ. `None` = « selon `config.yaml` », et **ça ne pose pas la
    clé** (cf. l'avertissement du module).
    `equivalent` — l'équivalent en ligne de commande, pour l'infobulle ET pour le croisement
    de `tools/inventaire_drapeaux.py`. Vide quand il n'y en a pas.
    `cout` — ce que le paramètre coûte, **avec son dénominateur**, ou vide. C'est ce que le
    récapitulatif de lancement affiche ; un coût sans dénominateur ne s'affiche pas.
    `persiste` — la valeur survit-elle à la fermeture ? `False` pour `force`, `dry_run` et
    `shutdown` — cf. `gui/reglages.NON_PERSISTES`, dont le motif est chiffré.
    `attribut` — le nom sous lequel le panneau range le widget construit. Déclaré ici plutôt
    que dérivé de l'identifiant : les noms existants (`case_force`, `champ_lot`) sont ceux
    que les tests de l'interface nomment depuis le lot 18, et les renommer aurait été une
    réécriture gratuite dans un lot qui n'en promet aucune.
    `groupe` — la clé d'un groupe de `GROUPES`.
    `infobulle` — la phrase complète. L'équivalent CLI y est ajouté par le générateur.
    `choix` — `((libellé, valeur), …)` pour `genre=CHOIX`.
    `choix_dynamiques` — nom du jeu de valeurs que le panneau fournit à la construction
    (`"langue"`, `"modele"`, `"etape"`). Une liste de modèles ne peut pas être gelée dans une
    table : elle dépend de ce que le serveur répond.
    `minimum` / `maximum` / `pas` / `decimales` / `suffixe` — bornes du contrôle numérique.
    `special` — le texte de la valeur spéciale (`minimum`) d'un contrôle numérique. C'est là
    que « selon config.yaml » s'écrit pour un nombre, et `{defaut}` y est remplacé par la
    valeur lue dans le fichier.
    `exige` — identifiant d'un autre paramètre sans lequel celui-ci n'a pas de sens (`--conf`
    exige `--page`). Le générateur grise, il ne refuse pas en silence.
    """

    identifiant: str
    panneaux: tuple[str, ...]
    libelle: str
    genre: str
    defaut: object
    equivalent: str
    cout: str
    persiste: bool
    attribut: str
    groupe: str = "cible"
    infobulle: str = ""
    choix: tuple[tuple[str, object], ...] = ()
    choix_dynamiques: str = ""
    minimum: float = 0
    maximum: float = 0
    pas: float = 1
    decimales: int = 2
    suffixe: str = ""
    special: str = ""
    exige: str = ""

    @property
    def drapeau(self) -> str:
        """Le drapeau de ligne de commande seul — `--format` pour `« --format webtoon »`.

        C'est la clé de croisement de `tools/inventaire_drapeaux.py`. Vide quand le paramètre
        n'a pas d'équivalent (le choix de modèle n'en a pas : il n'existe qu'en mémoire)."""
        return self.equivalent.split()[0] if self.equivalent else ""

    @property
    def trois_etats(self) -> bool:
        """Le paramètre a-t-il un état « n'y touche pas » ? C'est le cas dès que son défaut
        est `None` — la valeur qui ne pose pas la clé."""
        return self.defaut is None


# --------------------------------------------------------------------------- #
#  Les valeurs déclarées ailleurs, citées ici pour ne pas les recopier
# --------------------------------------------------------------------------- #

#: Délai d'extinction par défaut, en secondes. **C'est celui de `core/cli.py`**
#: (`--shutdown-delay`, défaut 120) : deux défauts pour un même geste feraient qu'une
#: extinction lancée depuis l'écran n'attendrait pas le même temps qu'en ligne de commande.
DELAI_EXTINCTION = 120

#: Bornes du délai. En dessous de 5 s, `core/power.shutdown` remonte de toute façon à 5 —
#: annoncer moins serait annoncer faux. Au-delà d'une heure, l'extinction n'est plus la fin
#: du run mais un réveil, et le compte à rebours du bandeau devient du décor.
DELAI_MIN, DELAI_MAX = 5, 3600


def _cout_force() -> str:
    """Le coût de `--force`, avec son dénominateur. Cf. `docs/chiffres-de-reference.md`."""
    return ("reprend le tome à la détection — des heures sur un tome complet "
            "(ordre de grandeur du dépôt : ~1 h 15 à 3 h 30 pour un tome traduit avec "
            "raisonnement, config.yaml § manga.modeles)")


#: **La** table, dans l'ordre d'affichage à l'intérieur de chaque groupe.
CATALOGUE: tuple[Parametre, ...] = (
    # -- Ce qui va tourner ------------------------------------------------------------- #
    Parametre(
        "depuis", (LIGHT_NOVEL, MANGA, WEBTOON), "Reprendre à", CHOIX, None,
        "--from ÉTAPE", "", True, "choix_etape", "cible",
        choix_dynamiques="etape",
        infobulle="Réutilise le cache des étapes précédentes et refait celle-ci et tout "
                  "l'aval. Chaque entrée dit ce qu'elle coûte."),
    Parametre(
        "page", (MANGA, WEBTOON), "Planche unique", ENTIER, 0,
        "--page N", "", False, "champ_page", "cible",
        minimum=0, maximum=9999, special="toutes",
        infobulle="0 = tout le tome. Sinon, ne (re)traite que cette planche ; les autres "
                  "sont réutilisées depuis leur cache."),
    Parametre(
        "chapitre", (LIGHT_NOVEL,), "Chapitre unique", ENTIER, 0,
        "--chapitre N", "", False, "champ_page", "cible",
        minimum=0, maximum=9999, special="tous",
        infobulle="0 = tout le tome. Sinon, ne (re)traite que ce chapitre ; les autres sont "
                  "réutilisés depuis leur cache."),
    Parametre(
        "langue", (MANGA, WEBTOON), "Langue source", CHOIX, None,
        "--langue DOSSIER", "", True, "choix_langue", "cible",
        choix_dynamiques="langue",
        infobulle="Quel sous-dossier de langue lire sous sources/<Projet>/<Tome>/<format>/. "
                  "⚠ Elle choisit le MOTEUR D'OCR : manga-ocr ne sait lire que le japonais. "
                  "« selon config.yaml » laisse le run déduire la langue du dossier trouvé, "
                  "puis de manga.langue_source."),
    Parametre(
        "force", (LIGHT_NOVEL, MANGA, WEBTOON), "Tout refaire depuis zéro", BASCULE, False,
        "--force", _cout_force(), False, "case_force", "cible",
        infobulle="Ignore tout le cache et reprend le tome à la première étape, détection "
                  "comprise."),
    Parametre(
        "dry_run", (LIGHT_NOVEL, MANGA, WEBTOON), "Simuler sans traduire", BASCULE, False,
        "--dry-run", "aucun appel LLM de traduction", False, "case_dry", "cible",
        infobulle="Traverse tout le pipeline sans un seul appel LLM de traduction : pour "
                  "vérifier qu'un tome est lisible et bien découpé avant d'y passer des "
                  "heures."),
    Parametre(
        # ⚠ **MANGA et WEBTOON seulement.** Le light novel refuse ce mode, et le motif est
        # écrit dans `run.py` : il n'existe aucune surface de saisie manuelle pour de la prose,
        # et un roman rendu sans traduction porterait son texte source dans un .docx français.
        #
        # ⚠ **Trois états, donc `defaut=None`** : « selon config.yaml ». Ne pas cocher ne
        # REARME pas la traduction — c'est `llm.actif` qui décide, et une machine qui ne fera
        # jamais tourner de LLM l'écrit une fois dans le fichier. C'est ce qui permet de
        # persister la case sans qu'elle surprenne (contrairement à `force` ou `shutdown`,
        # dont le motif de non-persistance est chiffré).
        "sans_llm", (MANGA, WEBTOON), "Sans serveur LLM (bulles vides)", BASCULE, None,
        "--sans-llm", "aucun appel LLM ; les bulles sortent vides", True, "case_sans_llm",
        "cible",
        infobulle="Détection, nettoyage, OCR et rendu seulement. Les bulles sortent VIDES : "
                  "tu saisis les répliques dans la Retouche, et elles vont dans "
                  "traduction_manuelle.json, que le pipeline ne réécrit jamais. ⚠ Différent de "
                  "« Simuler sans traduire », qui SIMULE une traduction et écrit la sortie "
                  "comme si elle avait eu lieu."),
    Parametre(
        "verbose", (LIGHT_NOVEL, MANGA, WEBTOON), "Journal détaillé", BASCULE, True,
        "--verbose", "", True, "case_verbose", "cible",
        infobulle="Temps, jetons et vitesse par bloc, et écriture de perf.log dans le "
                  "dossier de build. Remplit le canal ⏱ du journal."),

    # -- Traduction par lots ----------------------------------------------------------- #
    Parametre(
        "lot", (MANGA, WEBTOON), "Planches par appel", ENTIER, None,
        "--lot N", "", True, "champ_lot", "lot",
        minimum=0, maximum=20, special="selon config.yaml ({defaut})",
        infobulle="1 = une planche, un appel. 20 fait 7 appels au lieu de 131 sur un tome — "
                  "mais l'unité d'arrêt propre ET l'unité de perte passent à 20."),
    Parametre(
        "think", (MANGA, WEBTOON), "Raisonnement", CHOIX, None,
        "--think NIVEAU", "", True, "choix_think", "lot",
        choix=(("selon config.yaml", None), ("désactivé", False),
               ("low", "low"), ("medium", "medium"), ("high", "high")),
        infobulle="Raisonnement du traducteur. Coûteux à une planche par appel ; c'est le "
                  "lot qui le rend abordable, la trace étant payée une fois par lot.\n"
                  "⚠ « selon config.yaml » ne touche à rien — les autres valeurs "
                  "outrepassent aussi l'endpoint de l'agent."),

    # -- Détection --------------------------------------------------------------------- #
    #
    # ⚠ Ces deux seuils **exigent une planche unique** : « un changement de seuil pour tout le
    # tome appartient à config.yaml, où il est tracé et relu au run suivant »
    # (`manga/orchestrator_manga.py:process_volume`). Le générateur grise donc les champs tant
    # que « Planche unique » vaut 0, plutôt que de laisser l'orchestrateur refuser après coup.
    Parametre(
        "conf", (MANGA, WEBTOON), "Seuil de confiance", REEL, None,
        "--conf S", "", False, "champ_conf", "detection",
        minimum=0.0, maximum=1.0, pas=0.05, decimales=2,
        special="selon config.yaml", exige="page",
        infobulle="Relance la détection de la planche visée à ce seuil, et implique "
                  "« Reprendre à : detection ». L'écriture n'a lieu que si elle améliore "
                  "vraiment la détection : plus de bulles n'est pas mieux.\n"
                  "Prévisualiser d'abord avec tools/apercu_detection.py --balayage, qui ne "
                  "coûte qu'une inférence."),
    Parametre(
        "iou", (MANGA, WEBTOON), "Seuil de recouvrement", REEL, None,
        "--iou S", "", False, "champ_iou", "detection",
        minimum=0.0, maximum=1.0, pas=0.05, decimales=2,
        special="selon config.yaml", exige="page",
        infobulle="Seuil de NMS pour cette même relance. Mêmes contraintes que le seuil de "
                  "confiance : une planche visée, et la détection refaite."),

    # -- Découpage de la bande --------------------------------------------------------- #
    Parametre(
        "fenetre_hauteur", (WEBTOON,), "Hauteur de fenêtre", ENTIER, None,
        "--fenetre-hauteur PX", "", True, "champ_fenetre_hauteur", "bande",
        minimum=0, maximum=20000, pas=120, suffixe=" px",
        special="selon config.yaml ({defaut} px)",
        infobulle="Hauteur des fenêtres de détection, pour les planches assez allongées "
                  "pour être découpées. Sans effet sur une planche paginée, qui n'est jamais "
                  "découpée.\n"
                  "Ce qu'elle achète : sur une bande 1080 × 10 000, une bulle de 400 × 500 px "
                  "arrive au réseau en 26 × 32 px sans fenêtrage — la limite de "
                  "détectabilité — contre 118 × 148 px à 2160 px de fenêtre.\n"
                  "⚠ Ce qu'elle coûte : une inférence par fenêtre. Mesuré sur les 9 bandes du "
                  "chapitre de référence, 7,1 s par bande fenêtrée contre 0,85 s pour une "
                  "inférence unique (config.yaml, § « Découpage des bandes TRÈS ALLONGÉES »)."),
    Parametre(
        "fenetre_recouvrement", (WEBTOON,), "Recouvrement", ENTIER, None,
        "--fenetre-recouvrement PX", "", True, "champ_fenetre_recouvrement", "bande",
        minimum=0, maximum=19999, pas=100, suffixe=" px",
        special="selon config.yaml ({defaut} px)",
        infobulle="Recouvrement entre deux fenêtres consécutives.\n"
                  "⚠ Il doit rester ≥ la plus haute bulle attendue — mesurée à 833 px sur le "
                  "corpus — sinon une bulle peut être coupée par toutes les coutures qui la "
                  "traversent. Raboté à 80 % de la hauteur de fenêtre par "
                  "manga/detection.py."),

    # -- Illustration ------------------------------------------------------------------ #
    Parametre(
        "nombre", (ILLUSTRATIONS,), "Images", ENTIER, 1,
        "", "", True, "champ_nombre", "image",
        minimum=1, maximum=64,
        infobulle="Combien d'images générer pour ce personnage. Le coût annoncé suit ce "
                  "nombre."),
    Parametre(
        "graine", (ILLUSTRATIONS,), "Graine", ENTIER, -1,
        "--graine N", "", False, "champ_graine", "image",
        minimum=-1, maximum=2_147_483_647, special="aléatoire",
        infobulle="« aléatoire » = une graine tirée à chaque image, notée dans le sidecar. "
                  "Une graine fixée rejoue la même image.\n"
                  "⚠ Elle ne se persiste pas : la graine d'hier appliquée à un autre "
                  "personnage produirait une reproductibilité qui ne reproduit rien."),

    # -- Modèle ------------------------------------------------------------------------ #
    #
    # ⚠ Aucun équivalent en ligne de commande, **et c'est exact** : aucune des quatre CLI ne
    # porte de `--modele`. Le choix est une mutation en mémoire de la spec des agents, comme
    # `--think` en est une de `manga.lot.think`. Le déclarer avec un faux drapeau ferait
    # échouer le croisement de l'inventaire — pour de bonnes raisons.
    Parametre(
        "modele", (LIGHT_NOVEL, MANGA, WEBTOON, ILLUSTRATIONS), "Modèle de ce run", CHOIX,
        None, "", "", True, "choix_modele", "modele",
        choix_dynamiques="modele",
        infobulle="Outrepasse le modèle de TOUS les agents de cette brique, pour ce run "
                  "seulement.\n"
                  "⚠ Rien n'est écrit dans config.yaml, et aucun poids n'est téléchargé. "
                  "L'endpoint déclaré par un agent (« reflexion ») est CONSERVÉ : seul le "
                  "nom du modèle change."),

    # -- Run de nuit ------------------------------------------------------------------- #
    # ⚠ **Pas d'`ILLUSTRATIONS` sur ces trois-là**, et c'est une mesure, pas un oubli :
    # `run_illustration.py` n'appelle PAS `cli.ajouter_flags_veille` — sa CLI ne porte ni
    # `--keep-awake` ni `--shutdown` (vérifié par `tools/inventaire_drapeaux.py`, 22
    # arguments, aucun des trois). Les offrir dans l'atelier créerait un levier sans
    # équivalent en ligne de commande, ce que `gui/__init__.py` interdit.
    Parametre(
        "keep_awake", (LIGHT_NOVEL, MANGA, WEBTOON),
        "Empêcher la mise en veille", BASCULE, False,
        "--keep-awake", "", True, "case_veille", "nuit",
        infobulle="Empêche la veille système ET la veille écran pendant le run — le flag "
                  "écran compte : quand l'écran s'endort, le GPU réduit sa fréquence "
                  "(symptôme observé : un bloc à 0,4 tok/s au lieu de ~50).\n"
                  "Levé automatiquement à la fin du run."),
    Parametre(
        "shutdown", (LIGHT_NOVEL, MANGA, WEBTOON),
        "Éteindre le PC à la fin", BASCULE, False,
        "--shutdown", "éteint la machine", False, "case_extinction", "nuit",
        infobulle="À la fin du run (succès OU erreur), programme l'extinction après un "
                  "délai annulable. Pas d'extinction si le run est arrêté proprement.\n"
                  "⚠ Décochée à chaque ouverture, quoi qu'ait fait la session précédente."),
    Parametre(
        "shutdown_delay", (LIGHT_NOVEL, MANGA, WEBTOON),
        "Délai avant extinction", ENTIER, DELAI_EXTINCTION,
        "--shutdown-delay SECONDES", "", True, "champ_delai", "nuit",
        minimum=DELAI_MIN, maximum=DELAI_MAX, pas=30, suffixe=" s",
        exige="shutdown",
        infobulle="Compte à rebours affiché dans le bandeau de run, avec un bouton "
                  "« Annuler l'extinction ». Même défaut qu'en ligne de commande."),
)


# --------------------------------------------------------------------------- #
#  Les drapeaux exposés AILLEURS que dans un formulaire de run
# --------------------------------------------------------------------------- #

#: `(fichier de CLI, drapeau) -> où l'interface l'offre`. Ce sont des drapeaux réellement
#: atteignables à l'écran, mais par un bouton, une entrée de menu ou le sélecteur de cible —
#: pas par une case du formulaire. Les ranger avec les non-exposés dirait faux ; les ranger
#: dans le `CATALOGUE` demanderait au générateur de fabriquer des boutons de menu.
AILLEURS: dict[tuple[str, str], str] = {
    ("run.py", "projet"): "sélecteur de cible du lanceur (liste des projets)",
    ("run.py", "tome"): "sélecteur de cible du lanceur (liste des tomes)",
    ("run.py", "--check"): "menu Aide › Diagnostic complet, et l'entrée de pied « Diagnostic »",
    ("run.py", "--test-llm"): "menu Aide › Tester la connexion LLM",
    ("run.py", "--stop"): "bouton « Arrêter proprement » du lanceur et du bandeau de run",
    ("run.py", "--import-glossary"): "menu Projet › Importer un glossaire",
    ("run.py", "--optimize-glossary"): "menu Projet › Optimiser le glossaire",

    ("run_manga.py", "projet"): "sélecteur de cible du lanceur (liste des projets)",
    ("run_manga.py", "tome"): "sélecteur de cible du lanceur (liste des tomes)",
    ("run_manga.py", "--format"): "la DESTINATION : « Webtoon » est ce panneau avec "
                                  "--format webtoon, « Manga » le même sans",
    ("run_manga.py", "--check"): "menu Aide › Diagnostic complet, et l'entrée de pied "
                                 "« Diagnostic »",
    ("run_manga.py", "--stop"): "bouton « Arrêter proprement » du lanceur et du bandeau de run",
    ("run_manga.py", "--assembler"): "bouton « Assembler CBZ/PDF » et menu Projet › Assembler",
    ("run_manga.py", "--optimize-glossary"): "menu Projet › Optimiser le glossaire",

    ("run_illustration.py", "projet"): "liste « Œuvre » de l'atelier d'illustration",
    ("run_illustration.py", "tome"): "l'atelier travaille à l'échelle de l'ŒUVRE ; la "
                                     "restriction à un tome reste en ligne de commande",
    ("run_illustration.py", "--phase"): "les deux boutons de l'atelier : « Préparer la "
                                        "requête » (phase prompt) puis « Valider et "
                                        "générer » (phase image)",
    ("run_illustration.py", "--personnage"): "la liste « Personnages illustrables »",
    ("run_illustration.py", "--cadrage"): "la liste « Cadrage »",
    ("run_illustration.py", "--par"): "le champ « Validé par » de l'écran de relecture",
    ("run_illustration.py", "--inventaire"): "la galerie de l'atelier, qui compte et pèse "
                                             "les images en permanence",
    ("run_illustration.py", "--garder"): "bouton « Garder » d'une vignette de la galerie",
    ("run_illustration.py", "--jeter"): "bouton « Jeter » d'une vignette de la galerie",
    ("run_illustration.py", "--purger"): "bouton « Purger les rejetées » de la galerie",
    ("run_illustration.py", "--check"): "menu Aide › Diagnostic complet",
    ("run_illustration.py", "--ecraser"): "l'atelier réécrit TOUJOURS requete.yaml : la "
                                          "phase 1 est refaite à chaque préparation, et la "
                                          "relecture qui suit est la porte humaine",
}


# --------------------------------------------------------------------------- #
#  Les drapeaux délibérément NON exposés — avec leur motif
# --------------------------------------------------------------------------- #

#: `(fichier de CLI, drapeau) -> motif`. **Le motif est la valeur, pas un commentaire** : un
#: drapeau rangé ici sans raison lisible est un drapeau oublié qu'on a fait taire.
#:
#: ⚠ `tests/test_inventaire_drapeaux.py` refuse un motif vide, et refuse une entrée qui ne
#: correspond à aucun drapeau réel — un motif qui survit au drapeau qu'il justifiait est un
#: faux avertissement, au sens de la règle §5 bis du contexte agent.
NON_EXPOSES: dict[tuple[str, str], str] = {
    # ⚠ **`run.py --sans-llm` existe et REFUSE**, lot 39. Le drapeau est déclaré sur la CLI du
    # light novel pour que `run.py --sans-llm` réponde par un message qui explique, plutôt que
    # par un « unrecognized arguments » qui ne dit rien — mais il n'a aucune forme à l'écran,
    # puisqu'il n'y a rien à offrir. Le motif du refus : il n'existe aucune surface de saisie
    # manuelle pour de la prose (la Retouche est un éditeur de PLANCHES), et un roman rendu
    # sans traduction porterait son texte source dans un .docx français.
    ("run.py", "--sans-llm"): "le light novel refuse ce mode et le dit à l'exécution : sans "
                              "éditeur de prose, un roman rendu sans traduction porterait son "
                              "texte source. La case n'existe que pour manga et webtoon",

    # -- Les trois drapeaux de service, communs aux quatre CLI ------------------------- #
    **{(cli, "--version"): "la version est dans le titre de la fenêtre et dans « À propos » ; "
                           "un drapeau qui imprime puis quitte n'a pas de forme à l'écran"
       for cli in ("run.py", "run_manga.py", "run_ocr.py", "run_illustration.py")},
    **{(cli, "--config"): "le chemin du fichier de configuration est un argument de DÉMARRAGE "
                          "de l'application (gui.py le passe à la fenêtre), pas un réglage de "
                          "run. Le changer en cours de session invaliderait les agents déjà "
                          "construits et le tome ouvert"
       for cli in ("run.py", "run_manga.py", "run_ocr.py", "run_illustration.py")},
    **{(cli, "--list"): "l'inventaire des œuvres est le PLAN-34, qui lui consacre une "
                        "destination entière ; le reproduire ici en liste déroulante ferait "
                        "deux inventaires dont un serait abandonné"
       for cli in ("run.py", "run_manga.py")},

    # -- Light novel -------------------------------------------------------------------- #
    ("run.py", "--all"): (
        "⚠ Le manque le plus visible de ce lot, et il est assumé. `--all` n'est pas un "
        "PARAMÈTRE, c'est un ENCHAÎNEMENT : `run._run_all_volumes` et "
        "`run_manga._run_all_chapitres` portent le pré-vol, l'isolation par chapitre et le "
        "bilan RAPPORT-SERIE.md, tous écrits pour une console (prints, codes de sortie, "
        "namespace argparse). L'exposer ici demanderait soit de recopier ces trois choses — "
        "deux vérités qui divergeraient — soit d'extraire la boucle dans un module de socle, "
        "ce qui est un lot en soi. Le run de nuit reste lançable sur UN tome depuis "
        "l'interface (anti-veille, extinction, compte à rebours) ; l'œuvre entière reste "
        "`run.py --all`. Cf. docs/mesures/lanceurs-2026-09-05.md §5."),
    ("run.py", "--render-only"): (
        "doublon d'un paramètre déjà exposé : « Reprendre à : rendu » réassemble les formats "
        "de sortie depuis le Markdown en cache, sans appel LLM. Offrir les deux ferait deux "
        "chemins pour un même geste, dont un seul serait testé"),
    ("run.py", "--plan"): (
        "diagnostic de développement — il imprime les chapitres détectés par langue puis "
        "quitte. Sa place est le diagnostic structuré du PLAN-36 L36.1, pas un formulaire de "
        "lancement"),
    ("run.py", "--diff-stages"): (
        "mesure la valeur ajoutée de chaque agent sur un tome DÉJÀ traité : c'est un outil de "
        "banc, du même rang que tools/banc.py, et aucun outil de banc n'est dans l'interface"),
    ("run.py", "--migrate-glossary"): (
        "réintègre des glossaires ANTÉRIEURS (.bak, export, œuvre sœur) — un geste de "
        "récupération, à faire une fois, avec des chemins que l'on tape. L'import ordinaire "
        "(--import-glossary) est, lui, dans le menu Projet"),
    ("run.py", "--remplacer"): (
        "modificateur de --migrate-glossary, donc non exposé pour la même raison. ⚠ Il IGNORE "
        "le glossaire actuel du projet : un tel geste ne doit pas être à un clic"),
    ("run.py", "--extract-glossary"): (
        "l'extraction relit un tome DÉJÀ traduit et enrichit le glossaire de l'œuvre : c'est "
        "une action de projet, pas un réglage de run. Le PLAN-34 lui donne sa place avec "
        "l'export de glossaire, qui n'existe pas encore — les livrer ensemble évite une "
        "entrée de menu qui ne sait qu'entrer"),

    # -- Manga -------------------------------------------------------------------------- #
    ("run_manga.py", "--all"): (
        "même motif que `run.py --all` ci-dessus : un enchaînement de chapitres, pas un "
        "paramètre de run. Cf. docs/mesures/lanceurs-2026-09-05.md §5"),
    ("run_manga.py", "--extract-glossary"): (
        "même motif que côté light novel : action de projet, reportée au PLAN-34 avec "
        "l'export de glossaire"),
    ("run_manga.py", "--psd-test"): (
        "outil de validation Photoshop — il écrit un PSD minimal d'un calque de texte et "
        "s'arrête. Le PLAN-33 le nomme explicitement comme « à laisser »"),

    # -- Scan (brique bêta) ------------------------------------------------------------- #
    #
    # ⚠ Le sort de la brique est tranché dans `docs/mesures/lanceurs-2026-09-05.md` §4 et
    # rappelé ici en une phrase : **non livrée dans ce lot**, faute d'une mesure qui autorise
    # à l'afficher au même rang que les autres. Le motif est le même pour ses quinze
    # drapeaux, il n'est donc écrit qu'une fois.
    **{("run_ocr.py", drapeau): (
        "brique SCAN — non livrée dans l'interface par ce lot. Décision écrite du 2026-09-05 "
        "(docs/mesures/lanceurs-2026-09-05.md §4) : la brique est bêta depuis la 1.4.0, sa "
        "seule mesure publiée est « ~2 h pour 270 pages, reprenable page par page », et "
        "aucune mesure de QUALITÉ de lecture n'existe. Une destination qui porterait « bêta » "
        "sans pouvoir dire ce que la lecture vaut promettrait un rang qu'on ne peut pas "
        "tenir ; une case dans le lanceur manga brouillerait deux pipelines distincts "
        "(run_ocr.py ≠ run_manga.py). Elle reste donc en ligne de commande, et le README le "
        "dit")
       for drapeau in ("projet", "tome", "--all", "--page", "--from", "--force", "--langue",
                       "--apercu", "--seuil", "--verbose", "--stop", "--list", "--check",
                       "--keep-awake", "--shutdown", "--shutdown-delay")},

    # -- Illustration ------------------------------------------------------------------- #
    ("run_illustration.py", "--forme"): (
        "la forme du champ texte est une MESURE de ce dépôt sur son corpus (lot 25), pas une "
        "préférence : la surcharger au clic invaliderait la comparaison qui l'a choisie. Elle "
        "reste en ligne de commande, pour un balayage"),
    ("run_illustration.py", "--langue-prompt"): (
        "même motif que --forme : c'est un axe de BANC (quelle langue de prompt donne la "
        "meilleure ressemblance), tranché par mesure et non par préférence de session"),
    ("run_illustration.py", "--rejouer"): (
        "rejoue une requête archivée et compare les octets du PNG — c'est un outil de "
        "reproductibilité, qui prend un chemin de fichier de provenance ; il appartient au "
        "banc"),
    ("run_illustration.py", "--telecharger"): (
        "autorise le téléchargement des poids, plusieurs Go. ⚠ C'est un geste "
        "d'INSTALLATION, avec sa licence et sa provenance : PLAN-36 L36.2, avec consentement. "
        "Le PLAN-33 l'interdit explicitement au lanceur"),
    ("run_illustration.py", "--liberer-vram"): (
        "POST /free sur ComfyUI — « ce n'est PAS le chemin nominal », dit son propre texte "
        "d'aide, et illustration.vram.decharger_image reste false. Un bouton qui rendrait la "
        "carte au milieu d'une session serait un levier hors chemin nominal"),
    ("run_illustration.py", "--repetitions"): (
        "modificateur de --liberer-vram, qui sert à relever un TAUX D'ÉCHEC (PLAN-30 L30.4). "
        "Il n'arme rien : le chiffre se lit, la décision s'écrit dans config.yaml"),
    ("run_illustration.py", "--oui"): (
        "saute la confirmation de --purger, pour un script. Une interface qui offrirait de "
        "sauter sa propre confirmation n'aurait plus de confirmation"),
}


# --------------------------------------------------------------------------- #
#  Lecture de la table
# --------------------------------------------------------------------------- #

def parametres() -> tuple[Parametre, ...]:
    """Toute la table, dans l'ordre de déclaration."""
    return CATALOGUE


def pour(panneau: str) -> tuple[Parametre, ...]:
    """Les paramètres d'un panneau, **groupés dans l'ordre de `GROUPES`**.

    C'est cet ordre-là que le générateur rend, et c'est aussi celui du parcours de
    tabulation : les deux se déduisent de la même table, donc ils ne peuvent pas diverger."""
    rang = {cle: n for n, (cle, _) in enumerate(GROUPES)}
    choisis = [p for p in CATALOGUE if panneau in p.panneaux]
    return tuple(sorted(choisis, key=lambda p: rang.get(p.groupe, len(rang))))


def par_identifiant(panneau: str, identifiant: str) -> Parametre | None:
    for parametre in pour(panneau):
        if parametre.identifiant == identifiant:
            return parametre
    return None


def groupes_de(panneau: str) -> tuple[tuple[str, str, tuple[Parametre, ...]], ...]:
    """`((clé, titre, paramètres), …)` pour les seuls groupes que ce panneau remplit."""
    sortie = []
    for cle, titre in GROUPES:
        dedans = tuple(p for p in pour(panneau) if p.groupe == cle)
        if dedans:
            sortie.append((cle, titre, dedans))
    return tuple(sortie)


def defauts(panneau: str) -> dict:
    """Les valeurs de départ d'un panneau. **`None` y reste `None`** — la valeur qui ne pose
    pas la clé. Un `dict` sans les `None` cacherait précisément l'état qu'on veut tester."""
    return {p.identifiant: p.defaut for p in pour(panneau)}


def persistables(panneau: str, valeurs: dict) -> dict:
    """Ce qu'on a le droit d'écrire dans le fichier de réglages ou dans un profil.

    ⚠ Le filtre est ici, dans la table, et **doublé** par `gui/reglages.nettoyer()` et
    `gui/profils.nettoyer()`. Trois barrages pour une même règle n'est pas de la redondance
    décorative : `nettoyer()` lave aussi un fichier ÉCRIT À LA MAIN, que cette fonction ne
    verra jamais."""
    garde = {p.identifiant for p in pour(panneau) if p.persiste}
    return {c: v for c, v in valeurs.items() if c in garde}


def non_persistes(panneau: str) -> frozenset[str]:
    """Les identifiants que ce panneau refuse de persister — `force`, `dry_run`, `shutdown`,
    `page`, `graine`.

    Le motif de `force` est chiffré et vaut pour les trois premiers : « une case cochée hier
    qui se retrouve cochée aujourd'hui, c'est un tome relancé depuis la détection — des heures
    de GPU pour un état que personne n'a redemandé »."""
    return frozenset(p.identifiant for p in pour(panneau) if not p.persiste)


# --------------------------------------------------------------------------- #
#  L'application au run — la seule fonction qui connaît la forme de config.yaml
# --------------------------------------------------------------------------- #

@dataclass(frozen=True)
class Demande:
    """Ce qu'un formulaire rempli demande au socle. Rendu par `appliquer()`.

    `config` est la copie MUTÉE (l'appelant a la charge de fournir une copie profonde) ;
    `arguments` sont les paramètres de `tache_run` ; `energie` sont les trois réglages de run
    de nuit, que la FENÊTRE tient — pas la tâche, parce que le compte à rebours d'extinction
    doit rester annulable après la fin du run."""

    config: dict
    arguments: dict = field(default_factory=dict)
    energie: dict = field(default_factory=dict)
    #: Les agents dont le modèle a été outrepassé, `(nom, avant, après)`. Vide quand aucun
    #: modèle n'a été choisi. Le récapitulatif de lancement les NOMME : un run qui ne tourne
    #: pas sur le modèle de `config.yaml` doit le dire avant, pas après.
    agents_outrepasses: tuple[tuple[str, str, str], ...] = ()


def appliquer(config: dict, panneau: str, valeurs: dict, *,
              format_planche: str | None = None) -> Demande:
    """Écrit les valeurs du formulaire dans `config` (muté) et rend les arguments du run.

    ⚠ **`config` est muté sur place** : l'appelant passe une copie profonde, comme
    `PanneauLanceur._lancer` le fait depuis le lot 18. Le faire ici serait plus sûr, et ce
    serait faux : la copie doit englober aussi ce que l'appelant ajoute autour.

    ⚠ **La règle des trois états est appliquée ICI, et une seule fois.** Une valeur absente,
    `None`, ou égale à la valeur spéciale d'un contrôle numérique (`0` pour un pixel, `0.0`
    pour un seuil) veut dire « n'y touche pas » : la clé n'est **pas** posée. C'est ce que
    `tests/test_gui_parametres.py` vérifie clé par clé, sur un `config.yaml` réel.
    """
    lu = {p.identifiant: valeurs.get(p.identifiant, p.defaut) for p in pour(panneau)}

    def pose(identifiant):
        """La valeur, ou `None` quand elle veut dire « selon config.yaml »."""
        parametre = par_identifiant(panneau, identifiant)
        if parametre is None:
            return None
        valeur = lu.get(identifiant)
        if valeur is None:
            return None
        # ⚠ Un contrôle numérique à trois états dit « n'y touche pas » par sa valeur
        # spéciale, qui est son MINIMUM — jamais par un `None` que Qt ne sait pas produire.
        if parametre.trois_etats and parametre.genre in (ENTIER, REEL):
            if float(valeur) == float(parametre.minimum):
                return None
        return valeur

    # -- options communes -------------------------------------------------------------- #
    if "dry_run" in lu:
        config.setdefault("options", {})["dry_run"] = bool(lu.get("dry_run"))
    # ⚠ La règle des trois états : seul un `True` explicite arme le mode. `None` (« selon
    # config.yaml ») et `False` n'y touchent pas — désarmer depuis le formulaire une machine
    # qui a écrit `llm.actif: false` dans son fichier serait la contredire.
    if lu.get("sans_llm"):
        from core import cli as core_cli
        core_cli.appliquer_sans_llm(config, True)
    if "verbose" in lu:
        config.setdefault("options", {})["verbose"] = bool(lu.get("verbose"))

    # -- traduction par lots (manga / webtoon) ----------------------------------------- #
    if panneau in (MANGA, WEBTOON):
        bloc = config.setdefault("manga", {})
        planches = pose("lot")
        reflexion = lu.get("think")
        if planches is not None or reflexion is not None:
            lot = bloc.setdefault("lot", {})
            if planches is not None:
                lot["planches"] = int(planches)
            if reflexion is not None:
                lot["think"] = reflexion

    # -- découpage de la bande --------------------------------------------------------- #
    bande = {cle: int(v) for cle in ("fenetre_hauteur", "fenetre_recouvrement")
             if (v := pose(cle)) is not None}
    if bande:
        # ⚠ **Dans le bloc du FORMAT**, exactement comme `run_manga._appliquer_options_bande` :
        # `manga/formats.py:config_format` fusionne `manga.detection` avec
        # `manga.formats.<format>.detection`, le second l'emportant.
        cible = config.setdefault("manga", {})
        if format_planche:
            cible = cible.setdefault("formats", {}).setdefault(format_planche, {})
        cible.setdefault("detection", {}).update(bande)

    # -- le modèle de ce run ----------------------------------------------------------- #
    #
    # ⚠ Il outrepasse le `model:` de chaque agent de la brique, et **conserve l'`endpoint:`**.
    # Le piège est déjà documenté par le menu `--think` : « les autres valeurs outrepassent
    # aussi l'endpoint de l'agent ». Un sélecteur global qui écraserait en silence l'endpoint
    # « reflexion » serait pire que pas de sélecteur.
    modele = lu.get("modele")
    if modele:
        from core import modeles as mod
        demande_modele = mod.outrepasser(config, _section_du_panneau(panneau), str(modele))
    else:
        demande_modele = ()

    # -- arguments de `tache_run` ------------------------------------------------------ #
    #
    # ⚠ `0` = « tout le tome » pour la portée, et c'est une ABSENCE d'argument, pas un zéro :
    # `process_volume(only_page=0)` n'a pas de sens, et l'orchestrateur refuserait une planche
    # hors bornes après avoir chargé son modèle.
    portee = lu.get("page") if "page" in lu else lu.get("chapitre")
    arguments = {
        "force": bool(lu.get("force")),
        "depuis": lu.get("depuis"),
        "page": int(portee) or None if portee else None,
        "format_planche": format_planche,
    }
    for cle in ("langue", "conf", "iou"):
        valeur = pose(cle)
        if valeur is not None:
            arguments[cle] = float(valeur) if cle in ("conf", "iou") else valeur
    # ⚠ Les seuils EXIGENT une planche : c'est le contrat de `process_volume`, qui refuse
    # sinon. On ne les envoie donc pas quand la portée est le tome — plutôt que de laisser
    # l'orchestrateur lever après le premier chargement de modèle.
    if not arguments.get("page"):
        arguments.pop("conf", None)
        arguments.pop("iou", None)
    elif arguments.get("conf") is not None or arguments.get("iou") is not None:
        # …et ils IMPLIQUENT `--from detection`, comme en ligne de commande.
        arguments["depuis"] = "detection"

    # -- run de nuit ------------------------------------------------------------------- #
    energie = {"keep_awake": bool(lu.get("keep_awake")),
               "shutdown": bool(lu.get("shutdown")),
               "shutdown_delay": int(lu.get("shutdown_delay") or DELAI_EXTINCTION)}

    return Demande(config=config, arguments=arguments, energie=energie,
                   agents_outrepasses=tuple(demande_modele))


#: Où vit la spec des agents de chaque panneau. `None` = la racine de `config.yaml`, qui est
#: la section du light novel — et celle que la phase « prompt » de l'illustration utilise
#: (`illustration/orchestrateur.py` passe par `cli.models_in_config(config)` sans section).
_SECTIONS = {LIGHT_NOVEL: None, MANGA: "manga", WEBTOON: "manga", ILLUSTRATIONS: None}


def _section_du_panneau(panneau: str) -> str | None:
    return _SECTIONS.get(panneau)
