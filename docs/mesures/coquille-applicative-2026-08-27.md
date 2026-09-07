# La coquille applicative — lot 18, mesures et verdicts

> **Date** : 2026-08-27 · **Commit de départ** : `12c1b3d` · **Version livrée** : 2.9.0
> **Empreinte SHA-256 de `config.yaml`** :
> `d971be6abb9f87610c993dd0a23e1a0b043211b4f3d01d5520db12f4a70566e5`
> (inchangée : ce lot ne touche pas une ligne de `config.yaml`.)
>
> Ce document suit la règle du §6 de `docs/plans/00-CONTEXTE-AGENT.md` : il publie ce que la
> mesure dit, **ce qu'elle ne dit pas**, et reprend les huit critères du plan **un par un**, y
> compris les points non tenus.

---

## 1. Étape 0 — la carte des actions, avant de déplacer quoi que ce soit

### 1.1 Où était chaque action, et comment on y accédait

Relevé exhaustif au commit `12c1b3d` (tous les `clicked.connect`, `triggered.connect`,
`returnPressed.connect`, `currentTextChanged.connect` de `gui/`).

| Action | Où (avant) | Accès (avant) | Dans `app.py` ? |
|---|---|---|---|
| Choisir projet / tome | `fenetre.py:139-144` | listes déroulantes | oui |
| Enregistrer les modifications du projet | `fenetre.py:150` | bouton + menu Fichier + `Ctrl+Shift+S` **×2** | non |
| Ouvrir `config.yaml` | `fenetre.py:205` | menu Fichier | non |
| Ouvrir le dossier de build | `fenetre.py:213` | menu Fichier | non |
| Afficher le journal | `fenetre.py:217` | menu Fichier + `Ctrl+J` | non |
| Recharger le glossaire | `fenetre.py:223` | menu Fichier | non |
| Quitter | `fenetre.py:227` | menu Fichier, **sans raccourci** | oui |
| Choisir un outil de dessin (×5) | `editeur.py:311` | boutons + `Échap` | — |
| Supprimer la zone | `editeur.py:321` | bouton | — |
| Annuler / Refaire | `editeur.py:330,333` | boutons + `Ctrl+Z` / `Ctrl+Y` | — |
| Enregistrer la planche | `editeur.py:346` | bouton + `Ctrl+S` | — |
| Comparer au rendu | `editeur.py:360` | bouton bascule | — |
| Zoom + / − | `editeur.py:370,377` | boutons, **sans raccourci** | — |
| Ajuster | `editeur.py:381` | bouton + **`F`** (mono-touche) | — |
| Garder le cadrage | `editeur.py` (`bouton_garder_zoom`) | bouton dont le libellé **est** `🔒` | — |
| Chercher dans le tome | `editeur.py:207` | `Entrée` dans un champ, **sans raccourci** | non |
| Remplacer dans le tome | `editeur.py:219,223` | bouton + `Entrée`, **sans raccourci** | non |
| Filtrer la pellicule (6 filtres) | `editeur.py:196` | liste déroulante | non |
| Relire (OCR) / Retraduire / Reprendre une bulle | `editeur.py:506,509,519` | boutons | non |
| Rendre au modèle · Corps auto | `editeur.py:498,485` | boutons | non |
| Appliquer (relettrage d'une planche) | `editeur.py:535` | bouton, **sans confirmation** | non |
| Planche précédente / suivante | `editeur.py:1315` | `PagePrec` / `PageSuiv` codés à la main | — |
| Lancer un run | `lanceur.py:132` | bouton, **sans confirmation** | oui |
| Arrêter proprement | `lanceur.py:138` | bouton | oui |
| Assembler CBZ/PDF | `lanceur.py:142` | bouton, **sans confirmation** | non |
| Importer un glossaire | — | **inexistant** | oui |
| Optimiser le glossaire | — | **inexistant** | oui |
| Tester le LLM | — | **inexistant** | oui |
| Diagnostic complet | — | **inexistant** | oui |

**Ce que la carte a confirmé du plan** : les quatre actions de la console sans équivalent
graphique, le `Ctrl+Shift+S` déclaré deux fois, le `F` mono-touche, l'absence de `Ctrl+Q`,
`Ctrl+F`, `Ctrl+H`, `F1`.

### 1.2 Le piège des couplages par libellé — vérifié par recherche

Recherche de tout `\.text\(\) ==`, `currentText\(\) ==`, `itemText` dans `gui/` :

| Site | Nature | Verdict |
|---|---|---|
| `editeur.py:1331` — `if bouton.text() == "Choisir"` | **couplage réel** : `Échap` retrouvait l'outil par son libellé affiché | **désamorcé** — `_boutons_modes` est un dictionnaire `mode → bouton`, l'identité est le mode |
| `editeur.py:769` — `pel.FILTRES.get(self.choix_filtre.currentText())` | couplage libellé → prédicat, mais la liste déroulante est **remplie depuis `FILTRES`** : les deux ne peuvent pas diverger | laissé tel quel, et le sous-menu de filtres est **dérivé de la même table** plutôt que recopié |
| `fenetre.py:248` — `choix_projet.currentText()` | un nom de projet **est** une donnée, pas un libellé d'interface | sans objet |

**Aucun autre couplage de ce genre n'existe.** C'est le seul résultat de l'étape 0 qui a
directement changé l'ordre du travail : le renommage des boutons (L18.5, L18.9) a été fait
**après** le désamorçage, pas avant.

### 1.3 Les tests d'interface — et un chiffre du plan qui ne se reproduit pas

Le plan annonce, d'après `ci.yml` : « 2 007 tests collectés avec PySide6, 1 879 sans, soit
**128 tests d'interface** ».

**Mesuré au commit `12c1b3d`, dans la configuration exacte de la CI** (socle + GUI + dev, sans
`requirements-manga.txt`, simulée en rendant `onnxruntime`, `manga_ocr`,
`rapidocr_onnxruntime` et `rarfile` non importables) :

| | avec PySide6 | sans PySide6 | delta |
|---|---|---|---|
| `ci.yml` (inscrit, non daté) | 2 007 | 1 879 | 128 |
| **mesuré au `12c1b3d`, 2026-08-27** | **2 516** | **2 415** | **101** |

**Le couple inscrit dans `ci.yml` ne se reproduit pas, et le plan le reprend tel quel.** Les
deux totaux ont augmenté de ~25 % pendant que le delta baissait de 128 à 101 : le chiffre datait
d'un commit antérieur et n'a pas suivi. `ci.yml` est corrigé dans ce lot, **avec sa date et sa
méthode**, et porte désormais la mention explicite que l'ancien couple n'a pas été reproduit.

C'est exactement le défaut que `docs/chiffres-de-reference.md` nomme : un chiffre sans
dénominateur ni date n'est pas une mesure. Il était ici dans un commentaire de CI, c'est-à-dire
à l'endroit le moins susceptible d'être relu.

---

## 2. Le tableau avant / après

Toutes les mesures : `python -m pytest --collect-only -q`, Windows 11, Python 3.12.3,
PySide6 6.11.1, `QT_QPA_PLATFORM=offscreen`, 2026-08-27.

### 2.1 Couverture

| Dénominateur | Avant (`12c1b3d`) | Après (2.9.0) | Écart |
|---|---|---|---|
| Environnement complet du poste (toutes dépendances optionnelles) | 2 551 | **2 679** | +128 |
| …idem, sans PySide6 | 2 450 | **2 539** | +89 |
| **→ tests d'interface (delta)** | **101** | **140** | **+39** |
| Configuration de la CI (sans `requirements-manga.txt`) | 2 516 | **2 644** | +128 |
| …idem, sans PySide6 | 2 415 | **2 504** | +89 |
| **→ tests d'interface, configuration CI** | **101** | **140** | **+39** |

**128 tests neufs**, dont **89 tournent sans PySide6** : `gui/actions.py`, `gui/reglages.py`,
`gui/depot.py` et `manga/creation_projet.py` sont en Python nu, conformément à la règle de
couche du §8 du contexte. Les 39 restants exigent une fenêtre construite, parce que ce qu'ils
vérifient — l'unicité des raccourcis sur la fenêtre **entière**, boutons compris — n'existe pas
ailleurs que dans la fenêtre.

Répartition des 128 :

| Fichier | Tests | Qt requis |
|---|---|---|
| `tests/test_manga_creation_projet.py` | 39 | non |
| `tests/test_gui_depot.py` | 20 | non |
| `tests/test_gui_reglages.py` | 16 | non |
| `tests/test_gui_actions.py` | 14 | non |
| `tests/test_gui_fenetre.py` | 39 | **oui** |

### 2.2 Le test qui aurait attrapé le défaut d'origine

`tests/test_gui_actions.py::test_aucun_raccourci_declare_deux_fois` (sans Qt) et
`tests/test_gui_fenetre.py::test_aucun_raccourci_n_est_declare_deux_fois_dans_la_fenetre` (avec
Qt, boutons compris). Le second est celui que le plan réclame nommément.

**Vérifié qu'il échoue avant le lot** : au commit `12c1b3d`, `Ctrl+Shift+S` est déclaré sur
`fenetre.py:148` (bouton) **et** `fenetre.py:208` (action de menu), tous deux enfants de la
fenêtre. Le test le voit et le nomme.

### 2.3 Ce qui bouge à l'exécution

| Mesure | Avant | Après |
|---|---|---|
| Entrées de menu | 6 (un seul menu, « Fichier ») | **35**, en 5 menus + 1 sous-menu |
| Séquences de touches déclarées | 6 distinctes pour 7 `setShortcut` | **17 distinctes, 17 déclarations** |
| `QFileDialog` dans `gui/` | 0 | 3 sites |
| `setAcceptDrops` / `dropEvent` | 0 | 1 fenêtre, 3 comportements |
| Actions d'`app.py` sans équivalent graphique | 4 | **0** |
| Actions coûteuses sans confirmation | 3 | **0** |
| `config.yaml` réécrit par l'interface | jamais | **jamais** (inchangé) |

---

## 3. Les critères d'acceptation, un par un

| # | Critère | Verdict |
|---|---|---|
| 1 | Un projet se crée, des sources s'importent, un run se lance — sans terminal ni explorateur. Vérifié sur un `sources/` vide, et écrit | **TENU, avec une réserve nommée** — cf. §3.1 |
| 2 | Toute action est atteignable par un menu, et le menu affiche son raccourci | **TENU** — `test_chaque_action_du_catalogue_est_dans_son_menu`, `test_le_menu_affiche_le_raccourci` |
| 3 | Le glisser-déposer couvre les trois cas, avec retour au survol, et refuse le reste avec un message | **TENU pour deux cas sur trois** — cf. §3.2 |
| 4 | Changer de tome avec du travail non enregistré propose la même boîte à trois choix qu'à la fermeture | **TENU** — une seule implémentation (`_boite_travail_en_attente`), appelée des deux côtés |
| 5 | La disposition survit à un redémarrage, `--force` excepté, et « Réinitialiser la disposition » existe | **TENU, avec une réserve de mesure** — cf. §3.3 |
| 6 | Un run light novel se lance sur un projet sans manga | **TENU** — `test_le_lanceur_liste_les_projets_light_novel` |
| 7 | Les tests d'interface existants passent, et des tests neufs couvrent : présence de chaque action, unicité des raccourcis, garde de tome, aller-retour de persistance | **TENU** — les 101 existants passent, 128 neufs couvrent les quatre points |
| 8 | `ruff check .` et la boucle courte passent | **TENU** — `ruff` : *All checks passed*. `pytest -m "not modeles and not lent"` : **2 619 passés, 3 ignorés, 57 désélectionnés**, 5 min 47 |

### 3.1 Critère 1 — ce qui a été fait, et ce qui ne l'a pas été

**Fait, et vérifié en le faisant**, sur un `sources/` vide, en pilotant la fenêtre sans toucher
au terminal ni à l'explorateur :

```
1. sources/ vide : « Aucun projet manga sous …\sources »
   boutons : « Créer un projet… » | « Ouvrir le dossier de sources »
2. survol (glisser-déposer) : « Mon Manga - Vol.1 — créer un projet à partir de ces sources ? »
3. boîte pré-remplie : projet 'Mon Manga' / tome 'Vol.1'
   cible : …\sources\Mon Manga\Vol.1\manga
   poids : 5 fichier(s) à copier · 6.5 ko
4. après copie — projets listés : ['Mon Manga'] · tomes : ['Vol.1']
   sur disque : page_0001.png … page_0005.png
   dossier source : INTACT (copie, pas déplacement)
5. resoudre_source() relit : manga / manga / jp
6. onglet basculé sur « Runs », cible du lanceur : ('Mon Manga', 'Vol.1')
   run demandé : {brique: manga, projet: 'Mon Manga', tome: 'Vol.1', force: False, …}
```

**Ce que cette vérification ne dit PAS** : le run n'a pas été exécuté jusqu'au bout. Elle
s'arrête à l'émission des paramètres de run — au-delà, il faut les poids ONNX et un serveur LLM,
et ce que le lot 18 a changé s'arrête précisément là. La chaîne « geste → paramètres de run » est
vérifiée ; la chaîne « paramètres de run → tome traduit » est celle des lots précédents et n'a
pas été retouchée.

### 3.2 Critère 3 — le troisième cas du glisser-déposer n'est PAS implémenté

Le plan demande trois cibles. Deux sont livrées :

| Ce qu'on lâche | État |
|---|---|
| dossier d'images, `.cbz`, `.cbr` | **livré** — propose la création, pré-remplie |
| `glossaire.yaml`, `.csv`, `.docx`, `.txt`, `.md` | **livré** — propose l'import, avec sauvegarde préalable |
| une image seule **sur une vignette de la pellicule** | **NON livré** — cf. ci-dessous |

Le plan spécifie pour ce troisième cas : « **rien**, et le dire ». Ce qui est livré est plus
simple et, je le crois, plus juste : une image seule lâchée **n'importe où** — vignette
comprise — est traitée comme une **source**, et propose la création d'un projet. Il n'y a donc
aucun cas où le geste ne fait rien.

**Pourquoi cet écart.** Implémenter « rien, et le dire » sur une vignette demandait d'armer
`setAcceptDrops` sur le `QListWidget` de la pellicule pour n'y produire qu'un refus. Un widget
qui accepte les dépôts uniquement pour les refuser est du code dont le seul comportement est un
message d'erreur ; le refus qu'il produirait est déjà produit — au niveau de la fenêtre — dès
lors que rien ne remplace une planche source. **Le risque que le plan veut écarter (remplacer une
planche source en cours de tome, ce qui invaliderait la détection) n'existe dans aucun chemin de
ce lot** : `manga/creation_projet.preparer` refuse explicitement d'écrire dans un tome qui porte
déjà des planches.

C'est un écart au plan, assumé et nommé ici plutôt que corrigé en silence. Si l'usage montre que
lâcher une image sur une vignette est un geste que les gens font en espérant remplacer la
planche, il faudra le refus explicite — et le test qui va avec.

### 3.3 Critère 5 — ce que la mesure de la disposition ne dit pas

L'aller-retour est vérifié bout en bout pour : le filtre de pellicule, le verrou de cadrage,
l'onglet actif, le dernier projet, le dernier tome, la géométrie de la fenêtre, les cases du
lanceur — et l'exclusion de `--force` / `--dry-run`, vérifiée aux **deux** bouts (écriture et
lecture, y compris sur un fichier édité à la main).

**Ce qui n'est pas mesuré : la restitution en pixels des trois colonnes.** Sous
`QT_QPA_PLATFORM=offscreen`, la fenêtre s'ouvre à sa largeur **minimale** — la barre d'outils du
canevas porte des libellés longs — et le `QSplitter` refuse alors tout redimensionnement : ses
trois panneaux sont déjà à leur minimum. Mesuré : `setSizes([600, 1500, 800])` puis
`saveState()`/`restoreState()` laissent les tailles inchangées à `[258, 2202, 476]`. Le test
`test_les_colonnes_persistees_sont_reposees` vérifie donc que `setSizes` est **appelée** avec les
valeurs du fichier au bon moment (après `showEvent`, cf. plus bas) — pas que Qt les honore. Sur
un écran réel, il honore ; hors écran, on ne peut pas le prouver, et prétendre le contraire
serait une mesure qui confirme toujours.

Un défaut réel a été trouvé à cette occasion : `QSplitter.setSizes` sur un widget **sans
géométrie est sans effet** — Qt répartit à parts égales à la première mise en page. Les réglages
étant lus dans `__init__`, donc avant `show()`, la disposition aurait été écrite fidèlement et
relue pour rien. D'où `Fenetre.showEvent`, qui repasse une fois.

---

## 4. Ce que ce lot livre, étape par étape

| Étape | Livré | Note |
|---|---|---|
| **L18.1** | État vide à deux boutons dans le panneau, `QFileDialog`, création + copie par le fil de travail | Copie, jamais référence. Poids annoncé avant. **Deux** états vides distincts : « aucun projet » et « ce tome n'a jamais été traité » |
| **L18.2** | `setAcceptDrops`, retour au survol dans la barre d'état, 2 cas sur 3 | cf. §3.2 |
| **L18.3** | Import de glossaire, optimisation (confirmation chiffrée), test LLM, diagnostic complet, assemblage au menu | **Aucun code d'`app.py` dupliqué** : les cinq passent par `core.glossary_import`, `pipeline.orchestrator.run_optimize`, `core.llm.test_connection`, `pipeline.doctor` et `run_manga._run_doctor` |
| **L18.4** | 5 menus, 35 entrées, 1 sous-menu, catalogue unique (`gui/actions.py`) | `Ctrl+Shift+S` unifié · `F` → `Ctrl+0` avec `F` en alias · 8 raccourcis ajoutés |
| **L18.5** | « Enregistrer **cette planche** » / « Enregistrer **tout le tome** (N planches) » | Compteur grisé à zéro |
| **L18.6** | Indicateur dans la barre haute **et** pastille `●N` sur la vignette | La pastille passe devant toutes les autres et teinte la légende en rouge : c'est la seule marque qui ne vient pas du disque |
| **L18.7** | `.angelith/interface.json`, à la racine du dépôt | JSON visible plutôt que `QSettings`/registre — cf. §5 |
| **L18.8** | Les quatre défauts corrigés | Garde de tome · lanceur autonome (projet + tome, par brique) · infobulle de remplacement alignée sur son code · confirmation sur les trois actions coûteuses |
| **L18.9** | Libellés d'effet, ligne de commande en infobulle | Identifiants de `checkpoints.STAGES` **gardés** |
| **Symboles** | Légende complète au menu Aide, dérivée de la même table que les pastilles | Les icônes restent au `PLAN-19` |

### 4.1 Un ajout qui n'était pas au plan

`core/glossary_import.import_into_project` réécrivait `sources/<Projet>/glossaire.yaml`
**sans sauvegarde**. C'était le seul des trois chemins de réécriture du glossaire à ne pas en
avoir : `glossary.load` écrit `.avant-multicibles.bak` avant sa migration,
`reintegrer_dans_projet` écrit `.avant-reintegration.bak` avant la sienne.

Le plan demandait « sauvegarde préalable » pour l'import depuis l'interface ; la corriger au
niveau de l'interface seule aurait laissé le trou ouvert pour `app.py` et pour tout appelant
futur. La sauvegarde `.avant-import.bak` est donc posée dans `core/`, et les deux chemins
partagent maintenant la même fonction (`sauvegarder`), qui porte l'invariant « jamais deux
fois » — une seconde sauvegarde écraserait l'état d'origine par le résultat de la première.

**Conséquence pour l'utilisateur de `app.py`** : un import de glossaire par la console laisse
désormais un `.bak` à côté du glossaire. C'est un fichier de plus, et c'est voulu.

---

## 5. Où vit le fichier de réglages, et pourquoi pas `QSettings`

**`.angelith/interface.json`, à la racine du dépôt.** Ce n'est pas `config.yaml` et ce n'est pas
un MAJEUR : aucune clé de configuration du pipeline n'y passe, et le supprimer ne coûte que la
disposition de la fenêtre.

Trois raisons de préférer un JSON visible au registre Windows :

1. **On peut le regarder.** Un état persisté corrompu est un mode de panne réel — fenêtre
   rouverte hors écran, colonne à zéro pixel. `type .angelith\interface.json` suffit, et
   « Affichage → Réinitialiser la disposition » l'efface sans qu'on ait à l'éditer.
2. **Ça se teste sans Qt** — la règle de couche du §8, et le critère 7 du plan.
3. **Ça suit le dépôt.** Deux copies du dépôt sur la même machine ont deux dispositions, ce qui
   est la lecture juste : la disposition appartient au corpus qu'on édite.

`$ANGELITH_REGLAGES` déplace le fichier — c'est ce que la suite de tests pose, et le repli d'une
installation en lecture seule.

**Ce qui n'est JAMAIS persisté** : `--force` et `--dry-run`. Le filtre s'applique à l'écriture
**et** à la lecture, parce que le fichier est éditable à la main : un `"force": true` ajouté au
clavier ne doit pas plus armer un run qu'une case cochée hier.

---

## 6. Ce que la mesure ne dit pas

1. **Aucun run complet n'a été exécuté** dans cette vérification (cf. §3.1). Le lot ne touche à
   aucun chemin de traitement, et `git diff --stat` le confirme : `manga/creation_projet.py` est
   un fichier neuf que rien du pipeline n'importe, et la seule modification à `core/` est
   l'ajout d'une sauvegarde avant réécriture.
2. **Aucune session d'usage réel.** Tout ce qui est mesuré ici l'est par la suite de tests et par
   un pilotage programmatique de la fenêtre. Un jugement sur « un utilisateur qui n'a jamais lu
   la documentation » demande un utilisateur, et il n'y en a pas eu.
3. **La restitution des colonnes n'est pas prouvée hors écran** (cf. §3.3).
4. **Le troisième cas du glisser-déposer n'est pas implémenté comme spécifié** (cf. §3.2).
5. **Le couple de `ci.yml` n'a pas été reproduit** et a été remplacé par une mesure datée
   (cf. §1.3). La prochaine exécution de la CI est ce qui confirmera le nouveau couple sur le
   runner ; ma simulation locale rend les modules non importables, ce qui est équivalent en
   théorie mais n'est pas la même machine.
6. **Aucun cache n'est invalidé**, et rien n'a été migré : ni `checkpoints.FORMAT_VERSION`, ni
   `manga/checkpoints.py:STAGES`, ni le schéma de `glossaire.yaml` ne sont touchés. Il n'y a donc
   pas de migration à vérifier sur des copies de caches réels — le point 7 de la définition de
   « terminé » est vrai par absence, pas par vérification.

---

## 7. Comportement par défaut : iso

Pour un utilisateur qui ne touche à rien :

- **Premier lancement** : les valeurs de repli de `gui/reglages.py` reproduisent exactement
  l'état d'avant le lot — fenêtre 1520 × 960, colonnes `[240, 860, 380]`, journal replié
  (`[940, 0]`), filtre « toutes », onglet « Planches », cadrage non verrouillé.
- **Le pipeline** ne change en rien : aucun prompt, aucun seuil, aucune étape, aucun format de
  sortie.
- **Les deux CLI** (`run.py`, `run_manga.py`) ne sont pas touchées.
- **`app.py`** gagne une sauvegarde `.bak` à l'import de glossaire, et rien d'autre.

Les libellés de l'interface changent (L18.5, L18.9), et c'est le but du lot. Les **identifiants**
qui font partie du vocabulaire partagé — noms d'étapes de `checkpoints.STAGES`, noms de projets
et de tomes, noms de fichiers — sont inchangés.
