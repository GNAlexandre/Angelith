# PLAN 31 — Le démarrage ne charge rien : l'accueil, les destinations, le tome à la demande

> **Lire `00-CONTEXTE-AGENT.md`, puis `README-INTERFACE-31-37.md`.**
>
> **Nature attendue** — **MINEUR**. Aucun cache invalidé, aucune clé de `config.yaml` touchée.
> `docs/roadmap.md` le dit déjà pour la ligne « Menus and project management in the interface » :
> ajouter des menus ne casse rien, donc ce n'est pas un `3.0.0`.
>
> **Charge estimée** — 9 jours. C'est le plan le plus structurant de la série et le seul dont
> les six autres dépendent : il déplace la propriété du « tome courant ».
>
> **Prérequis** — aucun. **Bloque** les plans 32 à 37.
>
> ⚠ **Ce lot ne doit ajouter AUCUNE capacité de traitement.** Il déplace, il rend paresseux, il
> nomme. Un lot qui profite de la refonte pour glisser un paramètre de run n'est plus mesurable.

---

## 1. L'état, relevé à la source le 2026-09-04 (2.24.1, `8e5ee5a`)

### 1.1 Ce que `python gui.py` fait avant d'avoir affiché quoi que ce soit

La chaîne est courte et entièrement involontaire. Elle tient en quatre lignes de
`gui/fenetre.py` :

| Ligne | Ce qui se passe |
|---|---|
| L192 | `self.choix_projet.currentTextChanged.connect(self._remplir_tomes)` |
| L196 | `self.choix_tome.currentTextChanged.connect(self._ouvrir_tome)` |
| L167 | `self._remplir_projets()` — après `_construire`, donc les deux signaux sont armés |
| L421 | `self.choix_projet.addItems(projets)` → **`currentTextChanged` part** |
| L443 | `self.choix_tome.addItems(lister_tomes(...))` → **`currentTextChanged` part** |
| L445 | `_ouvrir_tome` : construit `Tome`, construit `Services`, appelle `editeur.ouvrir` |

`gui/modele_tome.py:lister_projets` rend une liste **triée**. Le premier projet par ordre
alphabétique est donc ouvert à chaque lancement, quelle que soit l'intention de
l'utilisateur — et « ouvrir » n'est pas une figure de style :

- `Tome(config, projet, tome)` lit l'index des planches (`index_planches`) ;
- `Services(config, projet, …)` est construit — c'est l'objet qui porte les **modèles chauds**,
  et la docstring de `Fenetre` dit exactement pourquoi il existe : « Sans eux, chaque clic sur
  *Retraduire* reconstruisait les agents et rechargeait le glossaire YAML » ;
- `self.editeur.ouvrir(self.tome)` (L471) peuple l'éditeur, donc la pellicule, donc
  `FilDeLecture` commence à composer des aperçus — `fenetre=10` par défaut
  (`gui.apercu.fenetre`), plafond de cache 120 Mo.

**L'utilisateur qui voulait seulement lancer un run a payé l'ouverture d'un tome qu'il n'a pas
choisi.** Et il l'a payée deux fois s'il change ensuite de projet.

⚠ **La garde `_tome_precedent` (L451-459) n'est pas le correctif** : elle empêche la
RÉOUVERTURE du même tome, pas la première. Elle a été écrite pour un autre défaut — les
signaux qui partent deux fois quand `_remplir_tomes` vide puis remplit la liste — et elle le
règle bien. Ne la retirez pas.

### 1.2 Ce que l'interface offre aujourd'hui comme structure

Trois onglets, dans un `QTabWidget` (L245-268) :

| Onglet | Panneau | Taille |
|---|---|---:|
| Planches | `gui/editeur.py:PanneauEditeur` | 107 206 o |
| Runs | `gui/lanceur.py:PanneauLanceur` | 20 544 o |
| Atelier | `gui/atelier.py:PanneauAtelier` | 53 313 o |

Et **une barre haute qui appartient à la fenêtre**, portant le couple projet/tome (L189-201).
C'est la source du couplage : le tome est un état de la FENÊTRE, que trois panneaux lisent.
L'onglet « Runs » a d'ailleurs dû se doter de **ses propres** listes projet/tome au lot 18
(`gui/lanceur.py` L78-88, commentaire L18.8.2), parce que celles de la barre haute sont
filtrées sur les tomes **manga** : « il n'existait aucun chemin d'interface pour lancer un run
light novel sur un projet qui n'a pas aussi du manga ». **Il y a donc déjà deux sélecteurs de
tome concurrents dans l'application**, et c'est un symptôme, pas un défaut à corriger sur
place.

### 1.3 Ce que les normes disent d'une application à six destinations

Deux sources, et elles convergent :

- **Fluent / WinUI `NavigationView`** : navigation **latérale** recommandée à partir de 5 et
  jusqu'à 10 catégories de premier niveau d'importance égale ; navigation **haute** en dessous
  de 5. Modes adaptatifs par largeur de fenêtre : ≥ 1008 px pane déployé, 641-1007 px
  compact (icônes), ≤ 640 px minimal (bouton menu). Les réglages vont **en pied** de pane.
- **NN/g** : la visibilité de l'état du système est la première heuristique ; un onglet est un
  conteneur, pas une destination, et trois onglets qui portent des métiers différents forcent
  l'utilisateur à deviner lequel « contient » ce qu'il veut faire.

Six destinations demandées par l'utilisateur (LN, manga, web, image, œuvres, modification)
**plus** un accueil : sept. On est dans la fourchette de la navigation latérale, et hors de
celle des onglets.

---

## 2. Étape 0 — peser le démarrage avant de le changer

### 0.1 — Ce que coûte le lancement actuel, chiffré

Rien de ce plan ne se défend sans ce tableau. Instrumentez `gui.py` et `gui/fenetre.py` avec un
chronomètre `time.perf_counter` (aucune dépendance nouvelle) et publiez, sur **le PC principal**
et sur un corpus réel (17 projets sous `sources/`, 15 sous `build/`) :

| Grandeur | Mesure attendue |
|---|---|
| temps `QApplication()` → `fenetre.show()` | s |
| dont `_remplir_projets` → `_ouvrir_tome` | s |
| nombre de fichiers lus avant le premier pixel | n |
| aperçus composés dans les 10 s qui suivent | n, et Mo de cache |
| `Services` construit ? glossaire YAML lu ? | oui/non, et sa taille |
| pic de mémoire résidente à l'ouverture | Mo |

⚠ **Mesurez avec le projet alphabétiquement premier tel qu'il est**, pas avec un tome
fabriqué : c'est ce tome-là que l'utilisateur paie. Nommez-le, avec son nombre de planches.

⚠ **Et mesurez le cas dégradé** : que se passe-t-il au lancement si ce premier tome est à
moitié traité, si son cache est d'une version antérieure (`load_regions` rend `None` sur écart
de `FORMAT_VERSION`), ou si son dossier a été renommé ? Un démarrage qui dépend de l'état d'un
tome arbitraire a des modes de panne arbitraires.

### 0.2 — Le nom des destinations, tranché avant d'être codé

L'utilisateur a nommé six entrées. Deux méritent d'être rediscutées **et le plan doit livrer un
verdict écrit**, pas un choix silencieux :

| Demandé | Proposé | Motif |
|---|---|---|
| LN | **Light novel** | déjà le libellé du `QComboBox` de `gui/lanceur.py` L74 ; un sigle en nav latérale ne se devine pas |
| MANGA | **Manga** | — |
| WEB | **Webtoon** | ⚠ « WEB » se lira « site web » une fois sur deux. Et voir L31.7 : ce n'est pas une brique |
| Génération d'Image | **Illustrations** | la destination montre un catalogue et une galerie (`PanneauAtelier`), pas seulement un bouton de génération |
| Gestion des Œuvres | **Œuvres** | une nav latérale nomme l'objet, pas l'activité |
| Modification | **Retouche** | « Modification » ne dit pas de quoi. Le panneau retouche des **planches** |

Plus **Accueil** en tête, et **Réglages** + **Diagnostic** en pied de pane, comme le veut la
convention Fluent. Publiez le tableau retenu ; c'est lui qui devient `gui/destinations.py`.

### 0.3 — Ce que la refonte met en danger, listé avant de commencer

Trois choses marchent aujourd'hui **parce que** le tome est un état de la fenêtre. Écrivez
comment chacune survit, avant la première ligne :

1. **la garde de travail non enregistré** (`_garde_changement_de_tome`, L480) — elle est armée
   sur le changement de **combo**. Après ce lot, on pourra quitter la retouche en changeant de
   **destination**, ce qui n'est pas un changement de combo. C'est un trou neuf, et c'est
   `PLAN-35` L35.4 qui le referme — mais ce plan-ci ne doit pas l'ouvrir sans le dire ;
2. **le verrou par planche** (`travailleur.py`, `marquer_verrou`) — une tâche de genre `run`
   porte `planche=None` et verrouille tout. Le fil unique et l'objet de signaux unique
   (`SignauxTravail`, créés une fois, cf. la docstring de `travailleur.py` sur les trois trous
   de concurrence de la 1.1.0) **restent propriété de la fenêtre**. Aucune destination ne crée
   de fil ;
3. **le catalogue d'actions** (`gui/actions.py`) — source unique des menus et des raccourcis,
   gardée par `tests/test_gui_actions.py` (unicité des séquences, existence d'une méthode
   `action_<identifiant>`). Les destinations s'y ajoutent, elles ne s'y substituent pas.

---

## L31.1 — Une table de destinations, en Python nu

`gui/destinations.py`, sans un import Qt, sur le modèle exact de `gui/actions.py` :

```python
@dataclass(frozen=True)
class Destination:
    identifiant: str        # "manga" — la fenêtre le relie à une fabrique
    libelle: str            # "Manga"
    icone: str              # clé de gui/icones.py
    raccourci: str | None   # Ctrl+1 … Ctrl+6, déclaré UNE fois, dans actions.py
    exige_tome: bool        # la destination a-t-elle besoin d'un tome ouvert ?
    pied: bool = False      # pane footer (Réglages, Diagnostic)
```

Ce que la table permet, et qui est le point :

- `tests/test_gui_destinations.py` vérifie **sans PySide6** qu'aucun raccourci n'est déclaré
  deux fois **en croisant avec `actions.sequences()`** — le `Ctrl+Shift+S` posé deux fois au
  lot 18 est exactement le défaut que cette table empêche de rejouer ;
- chaque identifiant a une fabrique dans la fenêtre, et le test le vérifie par `getattr`, comme
  `test_gui_actions.py` le fait déjà pour les actions.

⚠ **Les raccourcis restent déclarés dans `actions.py`**, pas ici. Deux catalogues de raccourcis
seraient deux vérités. `destinations.py` porte le **nom** du raccourci, `actions.py` la
séquence.

## L31.2 — La construction devient paresseuse, et c'est testable

Une destination est une **fabrique**, pas un widget : `QStackedWidget` + un dictionnaire
`identifiant → callable`, le panneau construit **au premier affichage** et gardé ensuite.

Trois panneaux existent et pèsent 181 Ko de Python à eux trois. Aujourd'hui les trois sont
construits au démarrage (L245-268). Après ce lot, un lancement qui reste sur l'accueil ne
construit **aucun** d'entre eux.

⚠ **Le précédent est dans le dépôt et il est bon** : le commentaire du lot 27 sur
`PanneauAtelier` (L262-264) dit « son constructeur ne charge aucun poids : le catalogue se
calcule en lisant des champs et en listant des fichiers. Un utilisateur qui n'ouvre jamais
l'onglet ne paie rien. » C'est vrai de son CONSTRUCTEUR ; ce lot le rend vrai de sa
CONSTRUCTION.

**Le test qui aurait échoué avant le lot** : après `Fenetre(...).show()`, `fenetre.tome is
None`, `fenetre.services is None`, et le dictionnaire de panneaux construits ne contient que
l'accueil. Il tourne avec `QT_QPA_PLATFORM=offscreen`, comme les 219 tests d'interface déjà
comptés par la CI.

## L31.3 — L'accueil, et il n'ouvre rien

Une page, six cartes (ou huit avec le pied), et **trois informations d'état** qui ne coûtent
rien à calculer :

1. **les œuvres récentes** — lues dans `.angelith/interface.json`, pas sur le disque. Deux ou
   trois entrées, chacune un bouton « Reprendre » qui ouvre la destination utile ;
2. **ce que la machine sait faire aujourd'hui** — endpoint LLM joignable, poids de détection
   présents sous `manga_models/`, Pandoc trouvable. **Aucun de ces trois tests ne bloque
   l'affichage** : voir L31.6 ;
3. **le rappel de version et d'état de brique** — `core/version.py:__version__` et
   `ETAT_BRIQUES`, déjà dans le titre de la fenêtre (L147). La brique scan est en **bêta** et
   l'accueil doit le dire là où l'utilisateur choisit.

⚠ **L'état vide reste celui du lot 18.** Quand `sources/` est vide, l'accueil porte les deux
boutons (« Nouveau projet », « Ouvrir sources ») que `PanneauEditeur.montrer_accueil` porte
aujourd'hui, et la ligne `warn` du journal reste émise (elle déplie le journal et s'affiche 8 s
dans la barre d'état). Ne remplacez pas un état vide qui marche par un plus joli qui en fait
moins.

## L31.4 — La barre haute disparaît, le tome descend dans les destinations

C'est l'étape risquée. Le couple projet/tome de la fenêtre (L189-201) est **supprimé**, et
chaque destination qui en a besoin porte le sien — `PanneauLanceur` en a déjà un, complet et
correct (L78-88), qui devient le modèle des autres.

La fenêtre garde exactement quatre choses :

| Ce que la fenêtre garde | Pourquoi elle seule |
|---|---|
| `FilDeTravail` + `SignauxTravail` | un seul fil ⇒ jamais deux écritures sur le même checkpoint |
| `FilDeLecture` | les compositions d'aperçu ne doivent pas attendre derrière un run |
| `Services` du tome ouvert en retouche | un par tome, cf. L466-468 : deux tomes peuvent viser deux endpoints |
| le journal, la barre d'état, la progression | un run se regarde d'où qu'on soit (`PLAN-32`) |

⚠ **`Services` reste créé par la fenêtre, à la demande de la destination**, pas par la
destination. C'est ce qui garde vraie la ligne « un `Services` par tome » et le
`self.services.liberer()` du changement de tome (L464).

⚠ **Un run en cours interdit le changement de tome, pas le changement de destination.** Les
combos sont déjà grisés pendant un run global (`_sur_debut`, L790-792) ; ce comportement se
déplace avec eux, il ne disparaît pas.

## L31.5 — La reprise, explicite

`gui/reglages.py` persiste déjà `dernier_projet` et `dernier_tome` (DEFAUTS, ~L80) et
`onglet`. Ce lot :

- remplace `onglet: 0` par `destination: "accueil"`, et **incrémente `VERSION`**. Le module
  ignore en bloc un fichier de version inconnue (« une disposition perdue coûte trois clics,
  une disposition à moitié appliquée coûte une session ») — c'est le comportement voulu, il n'y
  a **pas** de migration à écrire, seulement un test qui le prouve ;
- ⚠ **ne rouvre jamais le dernier tome tout seul.** `dernier_projet` / `dernier_tome`
  alimentent la carte « Reprendre » de l'accueil, un clic. C'est tout l'objet du lot : ce qui
  était implicite devient un geste.
- garde intacte la règle `NON_PERSISTES = {"force", "dry_run"}` — une case `--force` retrouvée
  cochée, ce sont des heures de GPU que personne n'a redemandées.

## L31.6 — Le démarrage ne demande rien au réseau

Les trois informations d'état de L31.2 sont des sondes : l'endpoint LLM
(`llm.base_url`, défaut `localhost:11434/v1`) est un appel réseau, et un Ollama arrêté répond
par un timeout, pas par un refus immédiat.

Règle, et elle est absolue : **aucune sonde ne s'exécute sur le fil d'affichage, et aucune ne
retarde le premier pixel.** Les sondes partent après `show()`, dans le fil de travail existant,
avec un délai d'attente court et **trois** états affichables — `joignable`, `injoignable`,
`inconnu (en cours)`. L'accueil s'affiche complet avec les trois marqueurs en « inconnu ».

⚠ **Ne réutilisez pas `_capturer_test_llm` (L1495) ni `_capturer_diagnostic` (L1476)** : ils
capturent la sortie CONSOLE d'un doctor dans un dialogue de texte. C'est le sujet du
`PLAN-36` L36.1, et le confondre avec une sonde d'accueil ferait de l'accueil une page qui
bloque plusieurs secondes.

## L31.7 — Le webtoon est une destination, et ce n'est **pas** une brique

À écrire dans le code, parce que c'est le mensonge le plus facile à livrer ici.

`run_manga.py` porte `--format {manga,webtoon}` (L129) : le webtoon est un **format** du même
orchestrateur, avec ses seuils propres (`manga.formats`, `SENS_PAR_DEFAUT`, le découpage des
bandes très allongées, `fenetre_hauteur: 2160`). `core/version.py:ETAT_BRIQUES` ne connaît
pas de brique « webtoon », et il a raison.

Donc : la destination « Webtoon » **est** le lanceur manga avec le format fixé et les réglages
de bande remontés. Trois exigences :

1. la docstring de la destination dit qu'elle partage l'orchestrateur, et nomme le drapeau
   équivalent ;
2. aucun code de traitement n'est dupliqué — la fabrique appelle le même panneau avec un
   paramètre, comme le `--format` de la CLI ;
3. ⚠ **la réserve mesurée du webtoon reste visible** : `docs/mesures/webtoon-2026-08-26.md`
   donne 15,1-17,0 % de fausses détections pour une cible de 5 %, et un sous-comptage à
   5,9 bulles par bande là où 25-35 seraient attendues. Une destination qui offre le webtoon
   au même rang que le manga sans afficher cet écart promet plus que ce qui est mesuré.

## L31.8 — Ce que voit un utilisateur qui n'a que le clavier

Le lot 19 a livré l'accessibilité (rôles, contrastes, ordres de tabulation déclarés par
panneau, `PARCOURS`). Ce lot ne doit pas la perdre :

- `Ctrl+1` … `Ctrl+6` atteignent les six destinations, déclarés dans `actions.py`, donc affichés
  dans le menu, donc gardés par le test d'unicité ;
- la nav latérale a un `PARCOURS` explicite comme les autres panneaux — « le critère 6 du
  `PLAN-19` demande UN ordre explicite PAR PANNEAU, pas un par défaut qui se trouve juste » ;
- chaque item de nav porte un `AccessibleName`, et l'état sélectionné est annoncé autrement que
  par la couleur.

---

## 3. Les critères de ce lot

1. Le tableau de l'étape 0.1 est publié : temps avant premier pixel, fichiers lus, aperçus
   composés, mémoire — **avant et après**, sur le même corpus, avec le nom et la taille du tome
   que l'ancien démarrage ouvrait.
2. Un test échoue avant le lot et passe après : après `show()`, aucun `Tome`, aucun `Services`,
   aucun aperçu demandé, et seul le panneau d'accueil construit.
3. Les six destinations plus l'accueil sont atteignables à la souris ET au clavier ;
   `tests/test_gui_destinations.py` tourne **sans PySide6** et croise `actions.sequences()`
   pour l'unicité.
4. La barre haute projet/tome de la fenêtre n'existe plus ; aucun panneau ne lit un tome qu'il
   n'a pas demandé ; `Services` reste unique par tome et libéré au changement.
5. `FilDeTravail`, `SignauxTravail` et `FilDeLecture` sont toujours créés **une seule fois**, et
   aucune destination n'en crée. Un test le vérifie par comptage d'instances.
6. `reglages.VERSION` est incrémentée ; un fichier de l'ancienne version est ignoré en bloc
   sans exception ; `force` et `dry_run` restent non persistés.
7. Aucune sonde réseau sur le fil d'affichage ; l'accueil s'affiche avec un endpoint LLM
   injoignable, et le dit, en moins d'une seconde.
8. La destination Webtoon nomme son format et affiche la réserve mesurée du corpus de bandes.
9. `tools/captures_gui.py` produit les captures de l'accueil et de deux destinations, sur le
   tome **synthétique** — jamais sur une des 17 œuvres, pour la raison que ce script écrit déjà.
10. `ruff check .` passe ; `pytest -q -m "not modeles and not lent"` passe ; le compte de tests
    est publié avec **son dénominateur** (`docs/chiffres-de-reference.md` fait foi).
11. `docs/mesures/coquille-<date>.md` reprend ces critères un par un, y compris les non tenus,
    et dit ce que la mesure ne dit pas.

## 4. Ce que ce lot ne fait pas

- Il n'ajoute **aucun** paramètre de run, aucun choix de modèle, aucun format de sortie. C'est
  `PLAN-33`.
- Il ne touche pas à la progression : la barre du bas reste ce qu'elle est. C'est `PLAN-32`.
- Il ne construit pas la bibliothèque d'œuvres : la destination « Œuvres » est livrée comme un
  **état vide nommé** qui renvoie vers les gestes existants (nouveau projet, ouvrir sources).
  C'est `PLAN-34`.
- Il ne modifie pas `gui/editeur.py` au-delà du strict nécessaire pour le recevoir comme
  destination. C'est `PLAN-35`.
- Il ne réécrit pas `config.yaml`, il n'y ajoute aucune clé, et il ne déplace pas
  `.angelith/`. C'est `PLAN-37` L37.4.
- Il ne fait pas entrer la brique scan (`run_ocr.py`) dans l'interface. C'est `PLAN-33` L33.5,
  et c'est une décision, pas un oubli.
