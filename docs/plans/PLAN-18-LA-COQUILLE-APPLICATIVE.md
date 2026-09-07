# PLAN 18 — La coquille applicative : l'interface cesse d'exiger la ligne de commande

> **Lire `00-CONTEXTE-AGENT.md` d'abord.**
>
> **Nature attendue** — MINEUR. Nouvelles capacités d'interface, aucun cache invalidé, aucune
> clé de configuration supprimée. ⚠ **Sauf L18.7** : persister l'état de l'interface introduit
> un fichier de réglages. Ce n'est pas `config.yaml`, donc ce n'est pas un MAJEUR — mais dites
> où il vit.
>
> **Charge estimée** — 12 jours.
>
> **Indépendant de tout.** Ce plan et `PLAN-19` (le système visuel) peuvent avancer en
> parallèle sur deux branches : celui-ci touche la structure et les actions, l'autre les
> couleurs et la typographie. **Faites celui-ci d'abord** si vous devez choisir : styler une
> interface dont il manque la moitié des actions revient à peindre une pièce sans porte.

---

## Le constat, en un scénario

Un utilisateur installe Angelith, lance `python gui.py`, et obtient : deux listes déroulantes
vides, un éditeur vide, une barre de progression vide. La seule instruction existante est un
message de journal :

> « Aucun projet manga trouvé sous `sources/` — dépose des images ou un `.cbz` sous
> `sources/<Projet>/<Tome>/manga/`. »

**Au crédit du code, ce message est émis au niveau `warn`** — il déplie donc le journal
automatiquement et s'affiche 8 secondes dans la barre d'état. Le premier lancement n'est pas
muet, et c'est mieux que ce que laisse croire une lecture rapide.

Mais c'est **une phrase de journal**, et elle décrit un geste à faire **ailleurs** : créer une
arborescence à la main dans l'explorateur de fichiers. Il n'y a ni écran d'accueil, ni bouton,
ni sélecteur de dossier — donc rien à cliquer, seulement une consigne à exécuter dans un autre
logiciel.

### L'inventaire de ce qui manque, vérifié par recherche

| Absent | Vérification |
|---|---|
| `QFileDialog` | **zéro occurrence** dans `gui/` — aucun sélecteur de fichier n'existe |
| `QInputDialog` | zéro |
| Glisser-déposer | zéro `setAcceptDrops`, zéro `dragEnterEvent`, zéro `dropEvent`, zéro `mimeData` |
| `QSettings` | zéro — rien n'est mémorisé d'une session à l'autre |
| `QToolBar`, `QDockWidget` | zéro — tout est en widgets posés dans des layouts |
| Menu Édition / Affichage / Projet / Aide | **il n'y a qu'un menu, « Fichier », à six entrées** |
| Boîte de préférences | aucune. Le seul réglage possible est « Ouvrir `config.yaml` dans l'éditeur système » |
| Liste des raccourcis | aucune. Il y a **sept `setShortcut` pour six séquences distinctes** — `Ctrl+Shift+S` est déclaré deux fois — plus `PagePrec`, `PageSuiv` et `Échap` codés à la main dans `keyPressEvent`. Aucun n'est documenté dans l'interface |

Et **quatre** actions du menu de la console `rich` (`app.py`) n'ont **aucun équivalent
graphique** : importer un glossaire, l'optimiser, tester le LLM, lancer le diagnostic complet.
(Les deux autres entrées de son menu — traiter un tome, demander l'arrêt propre — ont bien leur
équivalent, et l'assemblage CBZ/PDF existe déjà comme bouton de l'onglet « Runs ».)

---

## Étape 0 — Cartographier avant de déplacer

Une session de lecture, un document, aucun code.

1. **La carte des actions.** Pour chaque action que l'utilisateur peut déclencher aujourd'hui :
   où elle est (fichier:ligne), comment on y accède (bouton / menu / raccourci / geste), et si
   elle existe aussi dans `app.py`. Le tableau doit tenir sur une page.
2. **Les cinq fichiers de tests d'interface.** La CI atteste qu'ils existent et chiffre leur
   poids : **2 007 tests collectés avec PySide6, 1 879 sans**, soit **128 tests d'interface**.
   (Ne confondez pas avec le total du dépôt, 2 262 au 2026-08-25 — trois dénominateurs
   différents.) Trouvez-les, listez ce qu'ils couvrent. Vous en aurez besoin : ce plan déplace des actions, et un test qui vérifie un
   bouton par son libellé cassera.
3. **Le piège à désamorcer avant tout le reste.** `keyPressEvent` implémente `Échap` en
   comparant un **libellé affiché** :

   ```python
   if bouton.text() == "Choisir":
   ```

   Renommer ou traduire ce bouton casse la touche `Échap`. Cherchez les autres couplages du
   même genre **avant** de renommer quoi que ce soit.

Publiez la carte. C'est elle qui décide de l'ordre des étapes suivantes.

---

## L18.1 — Un chemin d'entrée : créer un projet depuis l'interface

**À faire.**

1. Un état vide **dans le panneau**, pas dans le journal : quand `sources/` ne contient aucun
   projet manga, l'onglet « Planches » affiche un message et **deux boutons** — « Créer un
   projet » et « Ouvrir un dossier de sources ». Aujourd'hui il affiche un aplat gris
   `QColor(40,40,44)` vide.
2. « Créer un projet » : un `QFileDialog` pour désigner des images ou une archive, un champ pour
   le nom du projet et du tome, et la création de `sources/<Projet>/<Tome>/manga/`. La brique
   sait déjà lire un dossier d'images, un `.cbz` et un `.cbr` — il ne manque que le geste.
3. **Copier ou référencer ?** Copier, et le dire. Un projet qui référence des fichiers hors de
   `sources/` casserait au premier déplacement, et le pipeline suppose l'arborescence.
   ⚠ Sur une archive de plusieurs centaines de mégaoctets, la copie doit passer par le **fil de
   travail** (`FilDeTravail`), jamais par le fil d'affichage.

**Critère.** Un utilisateur qui n'a jamais lu la documentation crée un projet et lance un run
sans quitter l'interface. À vérifier en le faisant, sur un dossier `sources/` vide, et à écrire.

---

## L18.2 — Le glisser-déposer

`setAcceptDrops` sur la fenêtre. Trois cibles, trois comportements :

| Ce qu'on lâche | Où | Effet |
|---|---|---|
| un dossier d'images, un `.cbz`, un `.cbr` | n'importe où sur la fenêtre | propose la création d'un projet (L18.1), pré-rempli |
| un `glossaire.yaml`, un `.csv`, un `.docx` | n'importe où | propose l'import de glossaire (L18.3) |
| une image seule | sur une vignette de la pellicule | **rien**, et le dire — remplacer une planche source en cours de tome invaliderait la détection |

⚠ **Un retour visuel pendant le survol est obligatoire**, sinon le geste paraît cassé une fois
sur deux. Et un lâcher de type inconnu doit produire un message, pas un silence.

---

## L18.3 — Ce qui existe dans la console et pas dans l'interface

Cinq actions à porter, en réutilisant le code d'`app.py` **sans le dupliquer** — s'il faut le
déplacer pour cela, déplacez-le vers `core/` ou `manga/`, conformément à la règle de couche.

| Action | Où elle est aujourd'hui | Où elle va |
|---|---|---|
| importer un glossaire (`yaml`, `csv`, `docx`) | `app.py`, saisie du chemin au clavier | menu **Projet**, plus glisser-déposer |
| optimiser le glossaire (dédoublonnage) | `app.py` | menu **Projet**, avec confirmation chiffrée |
| tester le LLM | `app.py` | menu **Aide** → « Diagnostic » |
| diagnostic complet (`--check`) | `app.py` | menu **Aide** → « Diagnostic », résultat dans un panneau |
| assembler CBZ/PDF | **déjà** un bouton de l'onglet « Runs » | y rester, **plus** une entrée de menu Projet |

⚠ **L'import de glossaire écrit dans `sources/<Projet>/glossaire.yaml`, qui est partagé avec le
light novel.** Une fusion malheureuse casse la cohérence de noms entre un roman et son manga.
Sauvegarde préalable — le projet a déjà ce patron, la migration multi-cibles écrit
`glossaire.yaml.avant-multicibles.bak` **avant** toute réécriture.

---

## L18.4 — Les menus, et la règle qui les gouverne

**La règle** : toute action de l'interface est atteignable par un menu, **et** garde son
raccourci et son bouton là où il est. Un menu n'est pas un rangement, c'est un **index
découvrable** — c'est aussi le seul endroit où un utilisateur apprend qu'un raccourci existe.

| Menu | Entrées |
|---|---|
| **Fichier** | Nouveau projet · Ouvrir un dossier de sources · *(sép.)* · Enregistrer la planche `Ctrl+S` · Enregistrer les modifications du projet `Ctrl+Shift+S` · *(sép.)* · Ouvrir le dossier de build · Ouvrir `config.yaml` · *(sép.)* · Quitter **`Ctrl+Q`** *(absent aujourd'hui)* |
| **Édition** | Annuler `Ctrl+Z` · Refaire `Ctrl+Y` · *(sép.)* · Rechercher dans le tome **`Ctrl+F`** · Remplacer dans le tome **`Ctrl+H`** *(les deux existent, aucun n'a de raccourci)* |
| **Affichage** | Zoom + / − / Ajuster `F` · Garder le cadrage · *(sép.)* · Comparer au rendu du pipeline · *(sép.)* · Filtre de pellicule (sous-menu, 6 filtres) · *(sép.)* · Journal `Ctrl+J` |
| **Projet** | Recharger le glossaire · Importer un glossaire · Optimiser le glossaire · *(sép.)* · Assembler CBZ/PDF · *(sép.)* · Préférences |
| **Aide** | Raccourcis clavier · Diagnostic · Tester le LLM · *(sép.)* · À propos (version, licence AGPL, provenance des modèles) |

**Deux corrections au passage.**

1. **`Ctrl+Shift+S` est déclaré deux fois** dans la même fenêtre — sur le bouton et sur l'action
   de menu, tous deux enfants de la fenêtre. Deux raccourcis identiques de portée fenêtre. Une
   seule déclaration : l'action de menu, et le bouton s'y branche.
2. **`F` est un raccourci mono-touche dans un panneau qui contient deux champs de saisie.** Il
   est aujourd'hui sauvé par le fait que les gestionnaires de touches sont neutralisés en cours
   de saisie — mais un raccourci mono-touche dans un formulaire est une bombe à retardement.
   Passez-le en `Ctrl+0` (convention) **en gardant `F`** comme alias.

**Raccourcis à ajouter** : `Ctrl+Q`, `Ctrl+F`, `Ctrl+H`, `F1` (aide), `Ctrl++` / `Ctrl+-` /
`Ctrl+0`, `Ctrl+Tab` (onglet suivant), `1`–`5` pour les cinq outils de dessin — **ceux-là aussi
mono-touche, donc soumis à la même prudence que `F`**.

---

## L18.5 — Deux boutons dont le nom promet la même chose

« Enregistrer la planche » (barre d'outils du canevas) et « Enregistrer les modifications du
projet » (barre haute de la fenêtre). La distinction n'existe **que dans une infobulle**, les
deux sont à deux extrémités de l'écran, et leurs raccourcis sont `Ctrl+S` et `Ctrl+Shift+S`.

Le code reconnaît d'ailleurs le problème pour un cas voisin déjà corrigé, mais les deux boutons
subsistent.

**À faire.** Un seul verbe visible, avec sa portée dans le libellé — « Enregistrer cette
planche » / « Enregistrer tout le tome » — et un compteur sur le second : « Enregistrer tout le
tome (3 planches) », grisé à zéro. Le nombre est déjà calculé (`planches_modifiees()`).

---

## L18.6 — Les gestes qui n'écrivent rien et ne le disent pas

Trois gestes ne produisent **aucun retour dans le panneau** : déplacer un bloc de texte, changer
le corps, retirer une correction manuelle. Ils écrivent une ligne dans un journal replié à zéro,
qui ne se déplie automatiquement que sur un avertissement :

```python
self.journal.emit("info", f"Planche {…} bulle {…} : position retenue — Ctrl+S pour l'écrire")
```

Les seuls indices restants sont le `[*]` du titre de fenêtre et une ligne d'état en gris 11 px.

**À faire.** Un indicateur de modification **dans le panneau**, à côté du bouton
d'enregistrement : « 3 modifications non écrites ». Et la pastille de la vignette concernée
change dans la pellicule — le mécanisme existe déjà (`pellicule.pastilles`), il suffit de
compter les brouillons.

---

## L18.7 — Persister l'état de travail

Sans `QSettings`, chaque lancement remet : la taille de fenêtre à `1520 × 960`, le journal
replié, les colonnes à `[240, 860, 380]`, le filtre sur « toutes », le verrou de cadrage
décoché, l'onglet « Planches » actif. Sur un tome de 150 planches, tout réglage de disposition
est à refaire à chaque session.

**À persister** : géométrie et état de la fenêtre, tailles des trois splitters, filtre courant,
verrou de cadrage, onglet actif, dernier projet et dernier tome ouverts, et les cases de
l'onglet « Runs ».

⚠ **Ne persistez pas ce qui a une conséquence coûteuse.** `--force` coché mémorisé, c'est un
tome relancé de zéro parce qu'une case était encore cochée d'hier. Cette case-là repart
décochée, toujours, et le dites en commentaire.

⚠ Et une entrée « Réinitialiser la disposition » dans le menu Affichage : un état persisté
corrompu doit avoir une sortie qui ne demande pas d'éditer un fichier à la main.

---

## L18.8 — Les incohérences à corriger pendant qu'on y est

Quatre défauts que la cartographie de l'étape 0 va rencontrer. Aucun n'est gros ; tous se
paient à l'usage.

1. **Changer de tome jette le travail non enregistré, sans un mot.** La fermeture de la fenêtre
   protège par une boîte à trois choix ; le changement de tome vide brouillons et documents
   inconditionnellement. Le seul filet est le miroir de récupération écrit toutes les 30 s.
   **Même boîte à trois choix qu'à la fermeture** — le code existe, il faut l'appeler.
2. **L'onglet « Runs » cible un tome qu'il n'a pas choisi.** Sa cible est une étiquette en
   lecture seule, remplie par la barre haute de l'onglet voisin, et la liste des tomes est
   **filtrée sur les tomes manga**. Choisir la brique « Light novel » ne change rien à cette
   cible : **il n'existe donc aucun chemin d'interface pour lancer un run light novel sur un
   projet qui n'a pas aussi du manga.** Corrigez le filtre selon la brique choisie.
3. **Une infobulle contredit son code.** Le champ de remplacement annonce « Remplace dans la
   RÉPLIQUE affichée » ; `_remplacer` applique sur toutes les planches, et la boîte de
   confirmation les nomme. Alignez l'infobulle sur le comportement.
4. **Trois actions coûteuses partent sans confirmation** : « Appliquer » relance
   `process_volume` sur une planche, « Assembler » réassemble, et « Lancer » démarre un run
   pouvant durer des heures — l'étape `detection` porte « des heures » **dans le libellé même**
   de son entrée de liste déroulante, ce qui est bien, et n'empêche rien. Le patron existe : le récapitulatif chiffré de « Enregistrer les modifications du
   projet » estime la durée sur une constante mesurée. Appliquez-le aux trois.

---

## L18.9 — Sortir du vocabulaire de la ligne de commande

L'interface parle aujourd'hui le langage de `run_manga.py` : cases nommées
`--force (ignorer tout le cache)`, `--dry-run`, `--verbose`, une infobulle qui renvoie
littéralement à `run_manga.py --page N --from …`, un bouton d'arrêt qui explique qu'il « écrit
le fichier STOP — comme `--stop` », et un menu dont l'intitulé est le nom d'un fichier
(`Ouvrir config.yaml`).

**À faire.** Le libellé dit **l'effet**, l'infobulle garde l'équivalent en ligne de commande —
qui est une information utile, pour qui script, mais ne doit pas être le nom de la commande.

| Aujourd'hui | Libellé | Infobulle |
|---|---|---|
| `--force (ignorer tout le cache)` | « Tout refaire depuis zéro » | « … équivaut à `--force` » |
| `--dry-run (aucun appel LLM…)` | « Simuler sans traduire » | « … `--dry-run` » |
| `--verbose (…et perf.log)` | « Journal détaillé » | « … `--verbose` » |
| « Ouvrir config.yaml dans l'éditeur système » | « Réglages avancés (fichier) » | « ouvre `config.yaml` » |
| « révision 3 → 4 » dans une boîte | « la planche a été modifiée sur le disque » | garder le numéro |

⚠ Les **étapes de reprise** (`rendu`, `traduction`, `terminologie`, `ocr`, `sfx`, `nettoyage`,
`detection`) sont un autre cas : ce sont des noms de `checkpoints.STAGES`, ils apparaissent dans
`RAPPORT.md` et dans la documentation. **Gardez l'identifiant**, il fait partie du vocabulaire
partagé — mais la glose de coût qui l'accompagne déjà est ce qui le rend utilisable.

---

## Les symboles, et pourquoi ils vont dans `PLAN-19`

L'information visuelle passe aujourd'hui par des caractères Unicode sans légende : `● ✎ ∅` dans
la liste de bulles, `∅ ⟳ ✎N ↔N ⚠N ·` sous chaque vignette, `⚠ ⏱ ·` en tête de ligne de journal,
et `🔒` comme **libellé complet** d'un bouton. Le sens n'est accessible que par survol.

**Ce plan ne les remplace pas** — les icônes appartiennent au système visuel. Mais il livre
**une légende** : un panneau dépliable sous la pellicule, ou une entrée « Légende des symboles »
dans le menu Aide. Le texte existe déjà (`etat_planches.libelle_etat`), il n'est simplement
jamais affiché ailleurs qu'en infobulle.

---

## Critères d'acceptation

| # | Critère |
|---|---|
| 1 | Un projet se crée, des sources s'importent, un run se lance — **sans jamais ouvrir un terminal ni l'explorateur de fichiers**. Vérifié sur un `sources/` vide, et écrit |
| 2 | Toute action de l'interface est atteignable par un menu, et le menu affiche son raccourci |
| 3 | Le glisser-déposer fonctionne pour les trois cas de L18.2, avec retour visuel au survol, et refuse le reste avec un message |
| 4 | Changer de tome avec du travail non enregistré propose la même boîte à trois choix que la fermeture |
| 5 | La disposition survit à un redémarrage, `--force` excepté, et « Réinitialiser la disposition » existe |
| 6 | Un run light novel se lance sur un projet sans manga |
| 7 | Les 128 tests d'interface existants passent, **et** des tests neufs couvrent : présence de chaque action de menu, unicité des raccourcis, garde de changement de tome, aller-retour de persistance |
| 8 | `ruff check .` et la boucle courte passent |

⚠ **Le critère 7 mérite un test qu'il faut écrire exprès** : un test qui parcourt la barre de
menus, collecte tous les `QKeySequence` déclarés dans la fenêtre, et échoue sur doublon. C'est
lui qui aurait attrapé le `Ctrl+Shift+S` déclaré deux fois, et c'est le genre de défaut qui
revient à chaque ajout de raccourci.

---

## Ce que ce lot ne fait pas

- Aucun changement de couleur, de police, d'icône ni de thème : `PLAN-19`.
- Aucun empaquetage, aucun installeur, aucune documentation anglaise — c'est un jalon distinct
  de `docs/roadmap.md`.
- Aucun changement au pipeline. Si une étape vous conduit à modifier `manga/` autrement que pour
  **déplacer** du code d'`app.py` vers une couche testable sans Qt, arrêtez-vous : vous êtes
  sorti du périmètre.
