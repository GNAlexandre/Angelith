# PLAN 34 — La bibliothèque des œuvres : l'état sur une page, le dépôt guidé, les exports

> **Lire `00-CONTEXTE-AGENT.md`, puis `README-INTERFACE-31-37.md`.**
>
> **Nature attendue** — **MINEUR**, avec un point d'attention : L34.4 crée un **export** de
> glossaire, donc un second producteur du schéma multi-cible établi en 2.0.0. Si l'aller-retour
> export → import n'est pas idempotent, ce lot devient une source de corruption de glossaire —
> et un glossaire perdu, c'est le travail de terminologie de plusieurs tomes.
>
> **Charge estimée** — 12 jours, dont 3 pour l'export de glossaire seul.
>
> **Prérequis : `PLAN-31`** (la destination « Œuvres » est livrée par lui comme état vide nommé).
> Indépendant du `PLAN-32` et du `PLAN-33` ; peut avancer en parallèle sur une autre branche.

---

## 1. L'état, relevé à la source le 2026-09-04 (2.24.1, `8e5ee5a`)

### 1.1 Le corpus réel

**17 projets sous `sources/`, 15 sous `build/`.** Un seul webtoon (`webtoon A` Chap.11),
qui est aussi le seul volume à source latine — les deux effets sont confondus, et plusieurs
mesures du dépôt en dépendent.

⚠ **Ce sont des œuvres sous droit d'auteur.** `tools/captures_gui.py` porte le raisonnement et
il vaut pour toute la bibliothèque : « une capture d'écran de l'éditeur montre une planche en
pleine page : la verser dans `docs/` reviendrait à publier une planche de manga dans le dépôt ».
Toute vignette produite par ce lot vit dans `build/` ou dans un cache local, **jamais** dans
`docs/`, jamais dans un artefact de CI, jamais dans une capture livrée.

### 1.2 Les briques de gestion qui existent déjà

| Brique | Fichier | Ce qu'elle fait |
|---|---|---|
| lecture d'un dépôt glisser-déposer | `gui/depot.py:classer` | rend `(verdict, chemins, message)` — sans Qt, testé |
| création de projet | `gui/dialogues.py:DialogueNouveauProjet` (L42) + `manga/creation_projet.py` | crée l'arborescence, copie les sources |
| ingestion | `manga/ingest.py` (`IMG_EXTS`, `list_source_files`) | images, `.cbz`, `.cbr`, `.zip` |
| état par planche | `manga/etat_planches.py` | ce qui est fait, ce qui est périmé |
| inventaire CLI | `run_manga.py --list` (L183) | l'inventaire existe **déjà**, en console |
| registre | `manga/registre.py` | — |
| rapport de série | `manga/serie.py` | rapport multi-tomes |
| import de glossaire | `core/glossary_import.py:import_into_project` | `.docx` / `.txt` / `.md` / `.csv` |
| réintégration de glossaire | `reintegrer_dans_projet` | un `.yaml` du projet, antérieur |
| optimisation de glossaire | `pipeline.orchestrator.run_optimize` | menu Projet, et `--optimize-glossary` |
| assemblage des sorties | `--assembler`, bouton « Assembler CBZ/PDF » | réassemble depuis `pages_out/` |
| formats manga | `manga/formats.py`, `manga/psd.py`, `manga/render_manga.py` | `images`, `cbz`, `pdf`, `psd` |
| formats LN | `pipeline/` + Pandoc / WeasyPrint | Markdown canonique → DOCX, EPUB, PDF |

Le glisser-déposer est **déjà armé sur la fenêtre entière** (`fenetre.py` L164), et le
commentaire dit pourquoi : « un lâcher est un geste qu'on fait *quelque part sur
l'application*, et le viser à 40 px près serait le rendre inutilisable ».

### 1.3 Les trois manques réels

**(a) Aucune vue d'ensemble.** Le seul inventaire du projet est `run_manga.py --list`, en
console. Pour savoir où en sont ses 17 œuvres, l'utilisateur ouvre les tomes un par un — et
avant le `PLAN-31`, l'application en ouvrait un tout seul au démarrage.

**(b) L'export de glossaire n'existe pas.** Vérifié : la seule fonction du dépôt dont le nom
commence par `export` est `tools/banc_sfx.py:exporter_crops` (L264), qui exporte des vignettes
de zones pour un banc. Le glossaire s'**importe**, se **réintègre** et s'**optimise**. Il ne
sort pas.

⚠ C'est pourtant l'un des six différenciateurs défendables du projet — « glossaire persistant
partagé roman ↔ manga (même `sources/<Projet>/glossaire.yaml`) » — et le seul qui ne soit pas
récupérable par l'utilisateur autrement qu'en ouvrant un fichier YAML à la main.

**(c) Les exports de rendu sont éparpillés.** `formats: ["cbz", "images", "psd"]` est une clé de
`config.yaml` (~L1838) appliquée pendant le run ; « Assembler CBZ/PDF » est un bouton de
l'onglet Runs ; le PSD par page est écrit sous `pages_psd/` ; les sorties LN sont produites par
le rendu du pipeline. Il n'existe aucun endroit où l'on voie **ce qui existe sur le disque
pour ce tome**, et rien ne dit ce qui est **périmé**.

---

## 2. Étape 0 — inventorier les 17 œuvres, et c'est le modèle de données

### 0.1 — Le tableau du corpus

Écrivez le script qui produit ce tableau, parce qu'il **est** la spécification de la vue :

| Œuvre | Tome | Brique | Format | Langue source | Planches / chapitres | Étapes faites | Sorties présentes | Glossaire (entrées) | Dernier run |
|---|---|---|---|---|---:|---|---|---:|---|

Contraintes, et elles font toute la difficulté :

1. ⚠ **aucun décodage d'image.** 17 projets × ~130 planches, c'est plus de 2 000 fichiers. Une
   vue qui ouvre les images est une vue qui met dix secondes à s'afficher. Les tailles se lisent
   dans les métadonnées de fichier, les états dans `.checkpoints/`, jamais dans les pixels ;
2. ⚠ **aucun appel LLM, aucun modèle chargé.** Le précédent est la docstring du lot 27 sur
   `PanneauAtelier` : « son constructeur ne charge aucun poids : le catalogue se calcule en
   lisant des champs et en listant des fichiers » ;

   > ⚠ **MISE À JOUR 2026-09-04 : ce précédent était FAUX, et il ne peut donc pas servir de
   > modèle tel quel.** L'étape 0 du `PLAN-31` l'a mesuré :
   > `PanneauAtelier.__init__` appelle `_remplir_projets` → `_sur_projet` →
   > `illustration.orchestrateur._glossaire`, qui lit `sources/<Projet>/glossaire.yaml` —
   > **26,9 Ko de YAML au démarrage**, pour un onglet que personne n'avait ouvert. La phrase
   > était vraie de son intention, pas de son code.
   >
   > Elle est vraie depuis le lot 31, mais pour une autre raison que celle qu'elle donne : ce
   > n'est pas le constructeur qui est devenu gratuit, c'est la **destination qui n'est plus
   > construite tant qu'on n'y va pas**. La contrainte ci-dessus reste la bonne ; le précédent
   > à citer est désormais `Fenetre._construire_page` et non le constructeur de l'atelier.
   > Cf. `docs/mesures/coquille-2026-09-04.md` §1, et
   > `tests/test_gui_atelier.py:test_l_atelier_ne_lit_plus_le_glossaire_au_demarrage`.
3. **mesurez le temps du balayage complet** sur les 17 projets, et le nombre d'appels
   `os.stat`. Si c'est au-delà d'une seconde, il faut un cache — et le cache a sa propre clé
   d'invalidation, à écrire.

### 0.2 — L'aller-retour du glossaire, avant d'écrire l'export

Le schéma est **multi-cible depuis la 2.0.0**, et ce changement a été un MAJEUR avec migration.
Avant la première ligne d'export :

1. relevez la **forme réelle** d'un `glossaire.yaml` du corpus — le plus gros des 17 —, avec
   son nombre d'entrées et les champs effectivement présents (pas ceux que le schéma autorise) ;
2. écrivez le test d'idempotence **d'abord** : `import_into_project(export(g)) == g`, sur les
   glossaires réels, en comparant les structures et non les octets ;
3. ⚠ **cherchez ce que l'export perdrait.** Un glossaire porte des accords grammaticaux, des
   formes dérivées à bannir, des variantes par langue cible. Un export CSV à plat les perd.
   **Le format d'archive est le YAML** ; les autres formats sont des **vues** en lecture, et
   l'interface doit le dire — « exporter en CSV » ne doit pas laisser croire qu'on peut
   réimporter le CSV sans perte.

### 0.3 — Ce qu'« œuvre » veut dire, tranché

Le dépôt a deux hiérarchies qui ne se recouvrent pas :

- `sources/<Projet>/<Tome>/manga/<LANGUE>/*.png` pour le manga et le webtoon ;
- `sources/<Projet>/<Tome>/<LANGUE>/…` pour le light novel ;
- et `gui/modele_tome.py:lister_tomes` filtre sur les tomes **manga** (`_est_tome_manga`), ce
  qui a déjà obligé le lanceur à se doter de ses propres listes (lot 18, L18.8.2).

**La bibliothèque doit lister les deux, avec leur brique.** Décidez et écrivez : une « œuvre »
est un dossier de `sources/`, qui porte un ou plusieurs tomes, chacun d'une brique déduite de
son arborescence — et un projet peut porter les deux (roman et manga partagent le glossaire,
c'est le différenciateur n° 1). La fonction de listage vit **hors de `gui/`**, parce que la
console en a besoin pour `--list`.

---

## L34.1 — Un modèle de bibliothèque, sans Qt et sans image

`core/bibliotheque.py` — dans `core/` et non `manga/`, parce qu'il couvre les deux briques.

```python
@dataclass(frozen=True)
class TomeInfo:
    projet: str
    tome: str
    brique: str            # "manga" | "webtoon" | "ln" | "scan"
    format: str | None
    langue_source: str | None
    unites: int            # planches, ou chapitres
    etapes: dict[str, str] # étape -> "faite" | "partielle" | "absente" | "perimee"
    sorties: dict[str, Path]   # "cbz" -> chemin, seulement si le fichier existe
    glossaire: int | None      # entrées, None si absent
    dernier_run: float | None  # mtime du checkpoint le plus récent
```

⚠ **`etapes` réutilise `manga/etat_planches.py` et `manga/checkpoints.py`**, il ne les
réimplémente pas. Une seconde lecture de l'état des checkpoints qui divergerait de la première
donnerait une bibliothèque qui affiche « fait » sur un tome que le pipeline va refaire.

⚠ **« périmée » a déjà un sens dans le dépôt** : `fenetre.py:_planches_perimees` (L647) et
`_demander_relettrage` (L691) le calculent pour les planches éditées après leur rendu. Réutilisez
ce sens exactement ; en inventer un second serait pire que ne rien afficher.

Et **`run_manga.py --list` rend cette structure** au lieu d'avoir sa propre lecture : un seul
inventaire, deux affichages. C'est la règle de couche du dépôt appliquée à l'endroit où on
l'oublie le plus facilement.

## L34.2 — La vue, et ce qu'elle refuse d'afficher

La destination « Œuvres » : une liste (pas des cartes à vignettes — voir plus bas), une colonne
d'état par étape, des filtres, et pour chaque tome les gestes qui le concernent.

| Colonne | Contenu | Source |
|---|---|---|
| Œuvre / Tome | nom | `sources/` |
| Brique | Manga · Webtoon · Light novel · Scan (bêta) | déduite de l'arborescence |
| Avancement | une pastille par étape, avec sa légende | `etapes` |
| Sorties | les formats **présents sur le disque** | `sorties` |
| Glossaire | nombre d'entrées | `glossaire` |
| Gestes | Lancer · Retoucher · Exporter · Ouvrir le dossier | destinations et actions existantes |

⚠ **Pas de vignettes de planches par défaut.** Deux raisons, et la première suffit : ce sont des
œuvres sous droit d'auteur, et une grille de couvertures est la capture d'écran qu'on ne pourra
jamais montrer (cf. `tools/captures_gui.py`). La seconde est le coût : 17 décodages d'image au
premier affichage. Si une vignette est livrée, c'est **désarmé par défaut**, et jamais dans une
capture du dépôt.

⚠ **La légende des pastilles est obligatoire.** `gui/dialogues.py:DialogueLegende` (L355) existe
déjà pour les symboles de l'éditeur — le lot 19 l'a livré pour cette raison exacte. Une pastille
sans légende est une couleur, et le lot 19 a aussi livré l'accessibilité : l'état ne se dit
jamais **par la couleur seule**.

## L34.3 — Le dépôt guidé, jusqu'au bout du geste

`depot.classer` décide déjà bien : `SOURCES`, `GLOSSAIRE`, `INCONNU`, et le message est
**toujours** rempli, « un geste réussi mérite autant d'être confirmé qu'un geste refusé
d'être expliqué ». Ce qui manque est ce qui vient après.

Le parcours à livrer, quand on lâche un dossier de planches ou un `.cbz` :

1. **ce que j'ai lu** — n fichiers, m images, formats, taille totale ; et pour une archive, son
   contenu **listé sans l'extraire** ;
2. **où ça va** — projet neuf ou tome ajouté à un projet existant, langue source, format
   (manga ou webtoon), le tout **prérempli par ce qui a été lu** et corrigible ;
3. ⚠ **copier, ne jamais déplacer par défaut.** Un lâcher qui vide le dossier d'origine est
   irréversible. « Déplacer » peut exister, décoché, nommé, confirmé ;
4. **la collision est nommée** — un tome qui existe déjà n'est pas écrasé en silence ;
5. **le compte rendu** — ce qui a été créé, où, et le geste suivant (« Lancer un run » ou
   « Fermer »).

⚠ **Le `.cbr` demande `unrar`/`unar`, qui n'est pas une dépendance pip.** Aujourd'hui l'échec
remonte comme une exception de `rarfile`. Le dépôt guidé doit dire « lecture des `.cbr`
indisponible : outil `unrar` absent » **avant** de proposer l'import, pas après l'avoir tenté.
La détection appartient au `PLAN-36` L36.1 ; ce lot la consomme.

## L34.4 — L'export du glossaire, qui n'existe pas encore

`core/glossary_export.py`, symétrique de `core/glossary_import.py`.

| Format | Statut | Pourquoi |
|---|---|---|
| **YAML** | format d'**archive** — aller-retour garanti | c'est le format du dépôt ; l'import existe déjà (`reintegrer_dans_projet`) |
| **CSV** | **vue**, perte assumée et écrite | le parseur d'import accepte tabulation et point-virgule ; l'export doit dire ce qu'il aplatit |
| **Markdown** ou **DOCX** | **vue** pour relecture humaine | le glossaire d'un tome est ce qu'on fait relire à un correcteur |

Trois exigences :

1. **le test d'idempotence de l'étape 0.2 est le critère du lot**, sur les glossaires réels du
   corpus, pas sur un exemple fabriqué ;
2. ⚠ **l'export nomme sa perte dans le fichier produit.** Un CSV exporté porte un en-tête de
   commentaire disant quelles colonnes du schéma n'y sont pas. Sans ça, quelqu'un le réimportera
   dans six mois et perdra ses accords ;
3. **l'export porte la provenance** : projet, tome, version d'Angelith, date, nombre d'entrées.
   C'est la règle des chiffres appliquée à un fichier qui va circuler — l'équipe de traduction
   se l'échangera, et un glossaire sans dénominateur ne se fusionne pas.

## L34.5 — Les exports de rendu, réunis sans être refaits

Un panneau d'export par tome, qui **n'exécute rien de neuf** :

| Sortie | Chemin d'exécution existant |
|---|---|
| images, CBZ, PDF (manga) | `--assembler` / `manga.render_manga.build_cbz`, `build_pdf` |
| PSD par page | déjà écrit pendant le run sous `pages_psd/` si `"psd"` est dans `formats:` |
| DOCX, EPUB, PDF (LN) | le rendu du pipeline, Pandoc et WeasyPrint |
| glossaire | L34.4 |
| rapport de série | `manga/serie.py` |

Les règles :

1. **ce qui existe est montré avec sa date et sa taille** ; ce qui n'existe pas est montré comme
   absent, avec le geste qui le produirait **et son coût** ;
2. ⚠ **un export qui exige un run le dit, et ne le lance pas tout seul.** Le PSD n'est pas
   « exportable » après coup : il est écrit par le run quand `formats:` le demande. Un bouton
   « Exporter en PSD » qui relancerait le rendu de 131 planches sans le dire serait la pire
   action coûteuse sans garde-fou de l'application — le lot 18 en avait déjà identifié trois ;
3. ⚠ **le PSD a une limite mesurée** : `manga/psd.py` refuse une planche au-delà d'une taille
   (« trois fois plus qu'une bande ordinaire », `config.yaml` ~L1800), et la 2.6.0 a livré ce
   refus **propre** plutôt qu'un fichier corrompu. Le panneau doit afficher ce refus comme un
   état, pas comme une erreur ;
4. **rien n'écrase sans confirmation**, et « Assembler » garde la confirmation que le lot 18 lui
   a donnée (L18.8.4).

## L34.6 — Ouvrir, et ne pas exposer

`_ouvrir_dans_le_systeme` (L997) existe et sert déjà pour `build/`, `config.yaml`, la bible et
les illustrations. Le panneau d'export le réutilise pour chaque sortie produite.

⚠ Et le rappel qui vaut pour tout ce lot : **aucun chemin de ce panneau ne verse un fragment
d'œuvre hors de `build/`**. Pas de « copier dans le presse-papier » d'une planche, pas de
vignette dans un rapport livré, pas de capture d'écran de la bibliothèque avec de vraies
couvertures dans `docs/`. Les captures se font sur le tome synthétique de
`tools/captures_gui.py`.

---

## 3. Les critères de ce lot

1. Le tableau des 17 œuvres de l'étape 0.1 est publié, produit par un script livré, avec le
   temps du balayage complet et le nombre d'appels `os.stat`.
2. `core/bibliotheque.py` ne connaît ni Qt, ni PIL, ni aucun modèle ; un test vérifie qu'un
   balayage complet **n'ouvre aucune image** (par instrumentation, pas par confiance).
3. `run_manga.py --list` consomme le même modèle que la vue. Sa sortie console est comparée
   avant/après : iso, ou le CHANGELOG dit ce qui change et pourquoi.
4. « Périmé » a exactement le sens de `_planches_perimees` ; un test le vérifie sur un tome
   fabriqué où une planche a été éditée après son rendu.
5. Le test d'idempotence export → import du glossaire passe sur **les glossaires réels du
   corpus**, en comparant les structures. Le plus gros des 17 est nommé, avec son nombre
   d'entrées.
6. Tout export non idempotent (CSV, Markdown, DOCX) porte, **dans le fichier produit**, la liste
   de ce qu'il perd, et sa provenance (projet, tome, version, date, nombre d'entrées).
7. Le dépôt guidé copie par défaut, ne déplace que sur une case explicitement cochée, nomme les
   collisions, et refuse un `.cbr` **avant** l'import quand `unrar` est absent.
8. Aucun bouton d'export ne lance un run sans confirmation nommant son coût. Le refus de PSD
   au-delà de la limite s'affiche comme un état.
9. Aucune vignette d'œuvre réelle n'est produite par défaut, et aucune capture livrée dans
   `docs/` n'en contient. Les captures utilisent le tome synthétique.
10. Les pastilles d'état ont une légende, et l'état ne se dit jamais par la couleur seule.
11. `ruff check .` passe ; `pytest -q -m "not modeles and not lent"` passe.
12. `docs/mesures/bibliotheque-<date>.md` reprend ces critères un par un, y compris les non
    tenus, et dit ce que la mesure ne dit pas.

## 4. Ce que ce lot ne fait pas

- Il ne produit **aucun** nouveau format de sortie. Il montre et il réunit ce qui existe.
- Il ne relance aucun run tout seul, jamais, sous aucun bouton.
- Il ne réécrit pas `config.yaml`, y compris la clé `formats:`. Choisir les formats d'un run est
  du `PLAN-33`.
- Il ne touche pas au schéma du glossaire — ni à `FORMAT_VERSION` des checkpoints. Un export ne
  change pas ce qu'il exporte.
- Il ne supprime rien. Pas de « supprimer un tome » dans ce lot : la corbeille d'une application
  qui gère des heures de GPU est un lot à elle seule, avec sa confirmation et sa réversibilité.
- Il n'affiche pas de couverture d'œuvre dans une capture, un rapport ou un artefact de CI.
