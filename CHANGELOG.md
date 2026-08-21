# Journal des modifications

Toutes les évolutions notables de Angelith sont consignées dans ce fichier.

Le format suit [Keep a Changelog](https://keepachangelog.com/fr/1.1.0/) et la
numérotation [SemVer 2.0.0](https://semver.org/lang/fr/), **précisée ci-dessous** pour
tenir compte de ce qui, dans ce projet, coûte réellement à l'utilisateur.

La version est déclarée **une seule fois**, dans [`core/version.py`](core/version.py) :
CHANGELOG, tag git, en-têtes de run, `perf.log`, `RAPPORT.md` et métadonnées des
fichiers produits en découlent. `tests/test_version.py` vérifie que `__version__`
correspond bien à la première entrée datée de ce fichier.

## Règle de numérotation

**MAJEUR** — l'utilisateur doit supprimer `build/` ou éditer `config.yaml` avant de
relancer la même commande : suppression/renommage d'un flag ou d'une clé de config sans
repli, changement de `.checkpoints/`, de `manga/checkpoints.py:STAGES` ou du schéma
`glossaire.yaml` **qui invalide les caches** (une relance de tome coûte des heures de
GPU), abandon d'un format de sortie, rupture du contrat de styles de
`templates/reference.docx`.

**MINEUR** — nouvelle capacité, rien ne casse : nouveau flag, nouvelle clé optionnelle à
défaut iso-comportement, nouvel agent/étape/format, nouveau garde-fou ou motif d'échec,
**et toute réécriture de prompt qui change le caractère de la traduction** (les prompts
ne sont pas du code mais déterminent la sortie ; il faut pouvoir faire
`git checkout v0.9.0 -- prompts/` pour reproduire la voix d'un tome — l'entrée de
changelog doit nommer le fichier).

**CORRECTIF** — aucun changement d'interface ni de sortie sur le chemin nominal : bug,
performance, refactor **prouvablement neutre** (même s'il déplace des centaines de
lignes), commentaires, README, tests, seuil d'heuristique, message d'erreur, coquille de
prompt.

> **La 1.0.0 fait exception.** Elle ne casse rien : elle marque la sortie de bêta de la
> brique manga, c'est-à-dire un état, pas une rupture. C'est le seul MAJEUR de ce dépôt
> qui n'oblige à supprimer ni `build/` ni quoi que ce soit. Les MAJEURS suivants obéissent
> de nouveau à la règle ci-dessus.

---

## [Non publié]

**Le dépôt devient publiable.** Aucun changement de comportement : ni flag, ni clé de config,
ni schéma de cache. Un run lancé avant cette entrée se relance après, à l'identique.

### Le projet s'appelle Angelith

`Yume-Trad` → `Angelith` partout — documentation, en-têtes de run, `perf.log`, métadonnées des
fichiers produits. **Deux exceptions délibérées** : les noms de modèles Ollama `yume-27b` et
`qwen3.5-9b-yumetrad` sont des noms *chez l'utilisateur*, pas des chaînes internes. Les
renommer casserait la config de quiconque a déjà créé le modèle. Ils restent, le README
explique que le nom est libre, et le basculement vers `angelith-27b` est reporté à la 2.0.0
avec message explicite au démarrage si l'ancien nom est détecté.

### Le corpus de mesure n'est plus nommé

Les mesures citées dans le code et la documentation nommaient les œuvres qui ont servi de
corpus. **191 occurrences dans 57 fichiers** sont remplacées par des désignations neutres et
stables (`manga A`, `roman A`…). Les chiffres, eux, sont tous conservés : ce sont eux qui
prouvent la qualité, et ils n'identifient rien.

Les glossaires de `sources/` sortent du suivi git. Ils y étaient ré-inclus délibérément depuis
l'origine — c'est du travail écrit à la main, et le perdre à chaque clone avait un vrai coût —
mais l'arbre git exposait le **nom de chaque œuvre comme nom de dossier**, ce qu'aucune purge
de contenu ne rattrape. Les fichiers restent sur le disque ; leur sauvegarde devient la
responsabilité de l'utilisateur, jusqu'à l'import/export prévu en 2.2.0.

⚠ **Les noms propres internes aux œuvres et les chaînes CJK ne sont PAS purgés.** Ils ne
désignent pas une œuvre par eux-mêmes, et plusieurs sont les témoins des tests de
normalisation des caractères (`ピカ`/`ヒカ`, `ガギグ`/`カキク`, paires kanji/kana) : les
remplacer aurait cassé ce que ces tests mesurent.

### Licence et conformité

- `LICENSE` (AGPL-3.0) à la racine, en-têtes SPDX `AGPL-3.0-or-later` sur **180 fichiers `.py`**
  (après le shebang), 2 `.ps1`, `config.yaml` et `templates/epub.css`.
- Les 8 `prompts/*.md` sont marqués **en fin de fichier**, jamais au début : un modèle lit le
  début de son prompt comme une instruction.
- `NOTICE` — dépendances tierces et leurs licences. PyMuPDF est en AGPL-3.0, ce qui est la
  *raison* de la licence du projet et non une préférence. Aucun poids de modèle n'est versionné.
- `templates/fonts/wildjess normal.ttf` sort du suivi : versionnée sans licence documentée et
  référencée nulle part dans le code. Écart consigné dans le `NOTICE`.

### Usage d'IA générative, déclaré

Section « Use of generative AI » au README, `docs/ai-provenance.md`, et une convention de
commit qui porte le modèle, la date et le prompt. Appliquée **dès ce commit** : un historique
de douze mois ne se documente pas rétroactivement.

### Documentation et gouvernance

`README.md` devient anglais et court (157 lignes) ; le README français de 132 Ko devient la
référence détaillée sous `docs/README.fr.md`, le mémo sous `docs/COMMANDES.fr.md`.
Ajout de `CONTRIBUTING.md`, `CODE_OF_CONDUCT.md`, `SECURITY.md`, `.github/FUNDING.yml` et
`docs/roadmap.md`.

### Reste à faire avant de publier

- **`templates/reference*.docx` contient 1 233 caractères de prose traduite.** Un gabarit
  Pandoc n'a besoin que de ses styles, mais `tests/test_render.py` en dépend : à vider avec
  précaution, pas à la volée.
- **L'historique git cite des œuvres** — 3 messages de commit, et les chemins
  `sources/<Titre>/` dans l'arbre de tous les commits. Le dépôt public doit partir d'un commit
  initial propre (`git checkout --orphan`), pas d'une réécriture approximative.

## [1.8.0] - 2026-08-21

**Le glossaire d'un manga se peuple enfin sans retraduire le manga.** MINEUR : deux nouveaux
flags sur `run_manga.py`, rien ne casse, **aucun cache invalidé**, aucune planche à refaire.

```powershell
python run_manga.py "Mon Manga" Vol.1 --extract-glossary   # un chapitre
python run_manga.py "Mon Manga" --all --extract-glossary   # toute l'œuvre (run de nuit)
python run_manga.py "Mon Manga" --optimize-glossary        # dédoublonnage (glossariste)
```

### Le défaut

Le glossaire est le **même fichier** pour les deux briques (`sources/<Projet>/glossaire.yaml`)
— c'est ce qui garde les noms cohérents entre un roman et son manga. Le light novel savait
depuis longtemps le peupler et le nettoyer sans rien retraduire (`--extract-glossary`,
`--optimize-glossary`). La brique manga, non.

La règle du relevé manga est pourtant juste, et on la garde : *une planche n'est relevée que
si elle va être traduite* — c'est elle qui garantit qu'un tome fini ne déclenche pas 150
appels par surprise. Mais elle avait une conséquence qu'on payait cher : sur une œuvre déjà
traduite, enrichir le glossaire imposait `--from traduction`, donc de **tout retraduire**.

| Ce qu'on voulait | Ce qu'il fallait payer |
|---|---|
| ~15 Ko de YAML | des heures de GPU, `pages_out/` réécrites, les CBZ réencodés (230 Mo par chapitre, sur un dossier OneDrive) |

### Ce que la commande fait, et ce qu'elle ne fait pas

| Tourne | Ne tourne pas |
|---|---|
| détection + OCR des planches qui n'en ont pas encore | nettoyage (`pages_clean/`) |
| relevé terminologique de **toutes** les planches | traduction, lettrage, rendu |
| dérive T1 (ancrée) et T2/T3 (volume) → `interdits` | `RAPPORT.md`, `projet.json` mis à part, CBZ/PDF |

Rien n'est écrit hors de `.checkpoints/` et du glossaire. C'est **testé** plutôt que promis
(`tests/test_manga_glossaire.py` compare les octets ET les `mtime` d'un chapitre complet) :
c'est la seule garantie qui rend la commande lançable sur une œuvre finie.

### Trois choix, et leur raison

* **Un MODE de l'orchestrateur, pas un second orchestrateur.**
  `process_volume(..., glossaire_seul=True)` réutilise le balayage A tel quel — migration du
  cache, scission bi-lobée, ordre de lecture, styles de bulle passés à l'OCR. Une copie de ces
  200 lignes aurait dérivé, et c'est le genre de dérive qu'on ne voit qu'au bout d'un tome.

* **Détection et OCR à la volée.** Un chapitre vierge n'est pas sauté : la commande sert aussi
  à établir le glossaire **avant** la première traduction, et pas seulement après.

* **Le dédoublonnage est payé UNE fois**, après le dernier chapitre, et seulement si le
  glossaire a réellement bougé (même empreinte que `_passe_terminologie`). Le glossariste
  travaille sur le glossaire entier de l'œuvre : le rappeler par chapitre, ce serait quinze
  appels pour un seul résultat.

### Ce qu'un chapitre déjà traduit rend possible

Les deux passes de dérive sont rejouées à partir du cache — l'OCR japonais face au français
déjà produit. Elles ne coûtent **aucun appel LLM** et remplissent les `interdits` que le
forçage attendait ; un `--from rendu` les applique ensuite aux 150 planches, toujours sans
LLM. Jusqu'ici, seules les planches qu'un run retraduisait y avaient droit.

### Ajouté

- `run_manga.py --extract-glossary` (chapitre nommé, ou `--all` pour l'œuvre) et
  `run_manga.py --optimize-glossary` (œuvre, sans tome).
- `manga/glossaire_manga.py` — points d'entrée de niveau run. ⚠ Les agents sont ceux de
  `manga.modeles` : passer par `pipeline.orchestrator.run_optimize` aurait ignoré le modèle,
  la température et l'`endpoint` réglés pour la brique manga.
- `orchestrator_manga.process_volume(glossaire_seul=…)`, plus `_passe_derive_volume` et
  `_passe_derive_ancree` (extraites, à comportement inchangé pour le run normal).
- `_passe_terminologie(ignorer_cache=…)` : rejoue un relevé en cache sur `--force` ou sur un
  `--from` dont la terminologie dépend (`ocr`, `detection`, `terminologie`). C'est la seule
  façon de reprendre un relevé après avoir modifié `prompts/terminologue.md` sans supprimer
  150 fichiers à la main.
- `tests/test_manga_glossaire.py` (13 tests) et 11 tests de dispatch dans
  `tests/test_run_manga_cli.py`.

### Ce que `--dry-run` veut dire ici, et pourquoi ce n'est pas ce qu'il veut dire ailleurs

Mesuré en préparant ce lot, sur *manga A* Vol.2 : un dry-run d'extraction sur
150 planches en cache fait **0 appel LLM** et pourtant **23 fusions** — et écrivait donc un
`termes_source` de plus dans le fichier de l'utilisateur. Re-fusionner des notes déjà en cache
change le glossaire sans qu'un modèle ait parlé.

Dans un run manga ORDINAIRE, `--dry-run` n'a jamais voulu dire « sans effet de bord » : il
écrit `ocr.json`, les pages nettoyées, les pages finales, le `RAPPORT.md` et le CBZ — seuls les
appels LLM sont neutralisés. Y enrichir le glossaire est donc cohérent, et le reste **inchangé**.

En mode `--extract-glossary`, le glossaire est la **seule** sortie du run : un dry-run qui
l'écrirait quand même ne laisserait plus rien à répéter en blanc. L'écriture y est donc
suspendue — et elle seule, le glossaire vivant normalement en mémoire.

Vérifié sur le tome réel, à l'octet près : 300 fichiers de `pages_out/` et `pages_clean/`, le
CBZ de 215 Mo, le `RAPPORT.md` et le glossaire, tous inchangés après un `--extract-glossary
--dry-run` sur les 150 planches.

### Détails qui comptent

- `--all --extract-glossary` est dispatché **avant** la branche `--all`. Sans cela il serait
  parti dans `_run_all_chapitres`, c'est-à-dire aurait retraduit l'œuvre entière — l'exact
  contraire de ce qu'il promet. C'est un test à lui seul.
- Le préchargement ne monte que le terminologue et le glossariste, jamais le traducteur : 17 Go
  de VRAM pour une commande qui ne traduit rien, et un déchargement final qui aurait évincé un
  modèle que l'utilisateur avait chargé pour autre chose. Même garde que `traduira`.
- Isolation par chapitre sur `--all` : un JPEG corrompu au chapitre 7 ne coûte pas les huit
  suivants (code de sortie 1, la série continue). L'arrêt **propre** reste franc.
- `--dry-run` fait la détection et l'OCR pour de vrai, mais n'écrit pas le glossaire : c'est
  une source de l'utilisateur, pas un artefact de build.
- Une dérive va en `interdits`, **jamais** en `variantes` — `variantes` est la clé de recherche
  du dédoublonneur, y déposer une faute corromprait une future fusion, silencieusement.

### Documentation

`README.md` §8 et §12 (« Cohérence des noms propres », point 3 bis), `COMMANDES.md`
(section « Glossaire » de la brique manga), docstring de `run_manga.py`.

---

## [1.7.1] - 2026-08-19

**La pellicule cesse de s'empiler sur elle-même.** Ouvrir un tome donnait une bande de
vignettes illisible pendant tout le chargement : images qui se chevauchent, tailles
incohérentes, légendes peintes par-dessus les images voisines. PATCH : aucune capacité
nouvelle, aucun cache invalidé, **aucune vignette à refabriquer**.

### ⚠ Corrigé : 2 767 paires d'items qui se recouvraient

La bande est un `QListWidget` en `IconMode`. Sans `setGridSize`, Qt dérive la position de
chaque item de la taille **réelle** de son pixmap. Un item pas encore vignetté mesure alors la
taille de son texte seul (~26 × 36 px) ; quand l'icône arrive, `QIconModeViewBase::dataChanged`
redimensionne son rectangle **sur place, sans refaire la disposition**. L'item grandit là où il
est, et recouvre ses voisins.

Reproduit hors écran plutôt que déduit, sur 150 planches, vignettes posées dans le désordre
comme le fait le fil de lecture :

| Panneau | Avant | Après |
|---|---|---|
| 240 px | **2 767** paires qui se chevauchent · **9 colonnes** · 78 ms | 0 · 1 colonne · 3 ms |
| 460 px | **3 819** paires qui se chevauchent · **22 colonnes** · 151 ms | 0 · 2 colonnes · 4 ms |

Neuf colonnes dans un panneau qui n'en tient qu'une : c'est la signature du défaut.

`setGridSize` fait calculer les positions sur une grille fixe. `setUniformItemSizes(True)`
devient cohérent une fois les tailles fixes, et n'est pas gratuit — Qt cesse d'interroger le
delegate item par item, d'où le facteur 26. Enfin un `sizeHint` posé **à la création** de
chaque item, avant même que sa vignette existe : la grille seule suffit à supprimer les
chevauchements, mais la hauteur d'item passe encore de 12 à 299 px à l'arrivée de l'icône, et
la bande tressaute pendant tout le chargement. Avec le `sizeHint`, rien ne bouge jamais.

Les dimensions de la cellule vivent dans `gui/pellicule.py`, à côté de `LARGEUR` : le
fabricant de vignettes et la bande qui les dispose doivent s'accorder, et c'est déjà tout le
rôle de cette constante.

**La cellule est fixe, l'image est centrée dedans.** L'autre voie — refabriquer les vignettes
sur un canevas de taille fixe — donnait le même résultat à l'œil et a été écartée : elle
imposait de réécrire ~150 JPEG par tome déjà ouvert, sur un dossier synchronisé. Une double
page laisse simplement du blanc au-dessus et au-dessous.

Un cadre d'attente neutre remplit la cellule tant que la vignette n'existe pas. Une cellule
vide serait à la bonne taille — la grille s'en charge — mais ne dirait pas s'il reste du
travail ou si la planche n'a rien à montrer.

### ⚠ Corrigé : des vignettes écrites sur disque qui n'atteignaient jamais l'écran

`composer_planche` fabriquait la vignette **puis** composait l'aperçu, et n'avait qu'un seul
code de retour pour les deux. Trois sorties perdaient donc une vignette déjà écrite : un aperçu
déjà en cache (`return False`), un scan source introuvable (`raise`), et toute exception de la
composition. Dans les deux derniers cas la planche entrait dans la mémoire d'échec du fil de
lecture et **son icône ne revenait plus de la session** — ce sont les cases restées vides dans
la bande.

Vignette et aperçu deviennent deux unités de travail distinctes (`GENRE_VIGNETTE`,
`GENRE_APERCU` — le vocabulaire existait déjà, seul l'ordonnanceur l'ignorait), avec deux
annonces distinctes. Et la mémoire d'échec devient **par genre** : un aperçu qu'on ne sait pas
composer ne condamne plus la vignette de sa planche, qui, elle, réussit très bien.

### ⚠ Corrigé : la bande restait vide pendant que les aperçus monopolisaient le fil

`_prochaine` triait par simple proximité, sans distinguer une **vignette** (quelques dizaines
de millisecondes, tout le tome) d'un **aperçu** (1,37 s médian, une fenêtre de 21 planches).
Les 21 aperçus passaient donc devant *toutes* les vignettes : une trentaine de secondes
pendant lesquelles la pellicule restait vide au-delà du voisinage immédiat.

Le CHANGELOG 1.5.0 énonçait pourtant la distinction — « deux portées délibérément
différentes » — mais elle ne vivait que dans la portée, pas dans la priorité. L'ordre est
maintenant en trois temps :

1. la planche **regardée**, entièrement — c'est la seule image sous les yeux de l'utilisateur ;
2. **toutes** les vignettes, à genre égal la plus proche d'abord — c'est la bande qui se
   remplit ;
3. les aperçus des voisines, à 1,37 s pièce, pour des planches où l'on n'est pas encore.

### Tests

+14 tests (1 726 hors `modeles`/`lent`). `tests/test_gui_pellicule_layout.py` est le premier test de widget du dépôt, et
l'exception est assumée : ce qu'il vérifie n'est pas un comportement mais une **géométrie** —
deux rectangles se recouvrent ou non. Il tourne hors écran en une seconde. Vérifié par
mutation : en remettant la configuration d'avant, six de ses huit tests tombent, avec 2 518 et
3 511 chevauchements et six tailles de cellule au lieu d'une.

`tests/test_gui_lecture.py` passe de 15 à 21 : six tests des deux natures de travail — l'ordre en trois
temps, l'aperçu qui lève sans emporter sa vignette, la mémoire d'échec par genre. Son atelier
factice ne modélise plus qu'un seul genre par défaut, ce qui laisse les quinze tests existants
dire exactement ce qu'ils disaient.

---

## [1.7.0] - 2026-08-19

**Une œuvre entière en une commande, et une nuit qui survit à ses accidents.** Traduire un
manga découpé en chapitres imposait une commande par chapitre, tapée à la main, en restant
devant. `run_manga.py --all` enchaîne l'œuvre, saute ce qui est déjà fait sans même l'ouvrir,
et n'abandonne plus quinze chapitres pour un JPEG tronqué. MINEUR : aucun cache invalidé,
aucune clé de config nouvelle ou obligatoire, aucune commande existante modifiée dans son
comportement — `perf.log` change seulement de condition d'écriture, dans le sens du plus.

### Nouveau : `run_manga.py "<Œuvre>" --all`

```
python run_manga.py "manga C" --all --keep-awake --shutdown
```

Le pendant manga du `--all` du light novel, avec trois différences que l'usage a imposées.

**Le pré-vol.** Le light novel ouvre chaque tome et laisse `process_volume` sauter les
chapitres finis. Côté manga, ouvrir un chapitre fini n'est pas gratuit : `assemble_outputs`
réécrit le CBZ **inconditionnellement** — 230 Mo pour *manga A* Vol.1, sur un dossier
OneDrive. `manga/serie.py` répond donc avant, en lecture seule : *autant de planches rendues
que de planches source, et aucune en retard sur ses données ?* Mesuré sur trois chapitres
déjà traités — **629 ms** pour tout constater, contre 3 min 9 s pour les rouvrir, et pas un
octet réécrit.

Les trois réponses qui existaient étaient toutes inutilisables. `--list` marquait « déjà
généré » sur la seule EXISTENCE du dossier de build : un chapitre arrêté à la planche 3 sur
150 passait pour terminé. Les empreintes SHA-256 de `projet.json` sont plus strictes, mais les
calculer demande de relire toutes les images — des minutes par chapitre, rien que pour
décider. Et l'ouverture coûte ce qu'on vient de dire.

**L'isolation.** Le light novel arrête la série au premier échec. Une nuit de manga rendrait
alors zéro chapitre pour un seul scan corrompu : chaque chapitre a son propre filet, et la
série continue. `SystemExit` y est rattrapé au même titre — c'est ce que lèvent un dossier de
chapitre vide et un modèle ONNX absent, deux accidents de chapitre, pas deux raisons de perdre
la nuit. L'arrêt PROPRE, lui, reste franc : `--stop` et Ctrl+C visent la série.

**Le bilan**, dans `build/<Œuvre>/RAPPORT-SERIE.md`, est **relu depuis le disque** après la
boucle et jamais tenu au fil de l'eau. C'est la seule version qui reste vraie quand un
chapitre s'est arrêté au milieu, ou qu'il s'est terminé en ayant perdu trois planches. Les
deux colonnes sont d'ailleurs croisées, sinon le tableau se contredirait lui-même : un
chapitre peut être « terminé » pour l'orchestrateur et `◐ partiel` sur le disque.

Le code de sortie vaut 1 si un chapitre a échoué **ou** si un chapitre traité reste
incomplet — mais pas après un arrêt demandé, où ce qui reste est ce qu'on a choisi de ne pas
faire. La seconde condition existe pour un cas que le filet par planche rend possible :
`process_volume` va au bout et renvoie « terminé » alors que toutes ses planches sont tombées.
Le code de retour dit « pas d'arrêt », le disque dit « rien de rendu » — c'est le disque qui
a raison.

### Le piège du chapitre « à relettrer »

Un chapitre dont le rendu est en retard sur ses données a un cache **complet** : rien n'y
manque, seul l'ORDRE d'écriture est en cause. Or `stages_to_redo` ne lit que la présence des
fichiers, jamais leurs `mtime` — il conclut « rien à faire », et `process_volume` saute chacune
de ses planches. Le chapitre serait donc ressorti « à relettrer » **après son propre passage**,
et chaque nuit l'aurait repris pour ne rien faire, en signalant un travail qui n'avance jamais.

`--all` nomme donc explicitement ce qu'il veut : `only_pages` sur les seules planches en
retard, plus `--from rendu`. C'est déjà ce que l'éditeur graphique demande après une
correction à la main, et ça évite de relettrer 150 planches pour une seule. `--force` et
`--from` reprennent la main quand ils sont donnés : l'utilisateur a nommé lui-même ce qu'il
veut refaire, et sur tout le chapitre.

### Nouveau : l'ordre de lecture des chapitres

`Chap.10` passait avant `Chap.2`. Ce n'est pas cosmétique : la passe terminologique enrichit
`sources/<Œuvre>/glossaire.yaml` au fil des chapitres, et les traiter dans le désordre
donnerait au chapitre 2 un glossaire nourri du chapitre 10.

`pipeline.sources._reading_order_key` ne pouvait pas servir — elle travaille sur `Path.stem`,
or `Path("Chap.5").stem` vaut `"Chap"` : tous les chapitres rendent la même clé, et l'ordre
obtenu était `Chap.10, Chap.2, Chap.5, Chap.1`. `ingest.natural_key` faisait déjà le bon
travail, elle est simplement appelée. `list_volumes` n'est pas touchée : elle sert au light
novel, dont les tomes sont nommés autrement.

### Nouveau : `--all --stop`, et `--list` qui dit la vérité

Le fichier `STOP` est **par tome** : un `--stop` nominatif ne pouvait arrêter qu'un chapitre,
donc rien du tout contre une série lancée depuis un autre terminal. `--all --stop` le pose
dans chaque chapitre déjà ouvert.

`run_manga.py "<Œuvre>" --list` remplace « (déjà généré) » par un verdict par chapitre :

```
   · Chap.6   28 planche(s) à traiter
   ✓ Vol.1    165 planche(s)
   ◐ Chap.9   12/28 planche(s)
   ↻ Vol.4    1 planche(s) à relettrer
   ⚠ Vol.2    aucune image ni archive
```

### ⚠ Corrigé : une planche en échec ne tue plus le tome

Les deux balayages de `process_volume` n'entouraient **rien**. Un JPEG tronqué à la planche 87
sur 150, une police introuvable au lettrage ou un `manga_ocr` qui lève faisaient remonter
l'exception jusqu'à la CLI : `assemble_outputs` n'était pas appelé, aucun `RAPPORT.md` n'était
écrit. Les checkpoints sauvaient le travail déjà payé en GPU, mais rien ne disait ce qui avait
échoué ni où reprendre.

La planche est désormais isolée, comptée, **nommée dans `RAPPORT.md`** avec sa commande de
reprise, et le tome va au bout — archive comprise. Vérifié en tronquant une planche source :
le chapitre rend son CBZ à 3 pages sur 4, le rapport dit `page 2 · étape « analyse » —
OSError : Truncated File Read · reprendre avec --page 2`, et la relance après réparation ne
recalcule que celle-là.

Une planche perdue au balayage A n'est plus retentée au balayage B : elle y échouait une
seconde fois sur une cause *dérivée* de la première (ni régions, ni page nettoyée, ni OCR),
se comptait deux fois, et noyait la vraie cause sous celle qu'elle avait provoquée.

`StopRequested`, `KeyboardInterrupt` et `SystemExit` traversent le filet — les avaler rendrait
`--stop` silencieusement inopérant et produirait 150 échecs identiques au lieu d'un message
clair.

### ⚠ Corrigé : les clients LLM abandonnés sur exception

Le light novel ferme ses clients dans un `except BaseException` depuis longtemps
(`pipeline/orchestrator.py`), la brique manga ne le faisait pas : une exception inattendue y
abandonnait les sockets Ollama **en pleine génération** — l'état que la docstring de
`LLM.close` relie à une chute persistante du débit GPU au run suivant, le pilote ne récupérant
proprement qu'au redémarrage.

`process_volume` devient une enveloppe de vingt lignes autour de `_process_volume`. En
enveloppe et non en `try`/`finally` autour du corps : celui-ci fait plus de mille lignes, les
réindenter d'un cran rendrait illisible tout diff ultérieur pour un gain nul.

### ⚠ Corrigé : `perf.log` n'existait que si `--verbose`

Le trou d'observabilité du projet. Un run lancé le soir sans ce flag ne laissait **aucune
trace fichier** — alors que `warn()` y écrivait déjà les incidents des clients LLM, les
débordements et les glyphes supprimés. Ces lignes partaient donc nulle part, précisément les
nuits où on en aurait eu besoin.

Le fichier et l'affichage sont découplés : `perf.log` est ouvert dès qu'on n'est pas en
dry-run, `--verbose` ne décide plus que de ce qui s'IMPRIME (`Reporter.set_console_verbose`).
`--all` va au bout de la logique — il force le calcul des mesures et laisse la console
silencieuse, ce que veut un run de nuit que personne ne regarde. S'y ajoute un journal de
série, `build/<Œuvre>/perf.log`, à suivre depuis un second terminal pendant que quinze
chapitres défilent.

### Harmoniser toute l'œuvre après la nuit

`--force` et `--from` neutralisent le saut du pré-vol — sans quoi la commande qui suit ne
toucherait aucun chapitre fini, c'est-à-dire exactement ceux qu'elle vise :

```
python run_manga.py "<Œuvre>" --all --from rendu
```

Le glossaire a grossi de tous les chapitres pendant la nuit. Cette passe relettre l'œuvre
entière avec sa version finale, **sans un seul appel LLM** — c'est le forçage `force: true`
déjà en place, appliqué à l'échelle de la série.

### Tests

+55 tests (1 712 hors `modeles`/`lent`, 52 avec). `tests/test_manga_serie.py` couvre les cinq
statuts, le comptage d'une archive `.cbz` par son index sans extraction, le `.cbr`
indénombrable qui vaut « à traiter », et le contrat non négociable : **le pré-vol n'écrit
rien**. `tests/test_run_manga_cli.py` couvre l'ordre, le saut, l'isolation, le cycle de vie du
modèle (préchargé et déchargé **une fois** pour la série) et l'écriture du bilan **avant**
l'extinction — `finalize_power` programme le `shutdown` puis dort tout le délai, un rapport
écrit après ne serait jamais écrit.

Deux tests existants changent de prémisse, et dans le sens du mieux :
`test_les_planches_d_un_lot_sont_ecrites_des_la_reception` ne guette plus un `RuntimeError`
qui ne remonte plus — il vérifie que le run **va au bout** en ayant sauvé les traductions, et
que le rapport nomme les quatre planches perdues. `test_l_orchestrateur_emprunte_bien_ce_chemin`
inspecte `_process_volume`, l'enveloppe ne contenant plus une ligne de rendu.

---

## [1.6.0] - 2026-08-19

**Ce que la 1.5.0 a cassé, et ce qui gelait la fenêtre** — la fermeture perdait du travail,
l'ouverture d'un tome figeait 888 ms, et un relettrage de trois planches jetait vingt et un
aperçus. MINEUR : aucun cache invalidé, aucune clé de config devenue obligatoire, aucun
changement en ligne de commande. `.recuperation/` est un dossier neuf qu'aucune brique ne lit.

### ⚠ Corrigé : fermer perdait le travail des autres planches

`Fenetre.closeEvent` appelait `enregistrer_document()`, qui n'écrit que la planche
**affichée**. La 1.5.0 ayant fait passer l'éditeur d'**une** planche ouverte à **N**, cinq
planches corrigées puis « Enregistrer et quitter » en sauvaient **une** et jetaient les
quatre autres — sans message, sans journal, sans trace. Le texte de la boîte l'avouait
d'ailleurs : « **La planche ouverte** porte des modifications non enregistrées ».

La cause est générale et vaut d'être nommée : `a_des_modifications()` est bien devenu
tomé-large en 1.5.0, mais ce qu'on en faisait ne l'était pas. `enregistrer_tout()` existait
déjà et fait exactement ce qu'il faut, refus par planche compris.

- La boîte **nomme** les planches (« Les planches 12, 27 et 40 portent… ») au lieu de les
  compter : « 5 planches en attente » n'apprend rien à qui veut savoir *si* la 27 est dedans.
- Une planche refusée (un run l'a réécrite) **annule la fermeture** et le dit. Partir sur un
  refus muet aurait été le même défaut sous un autre nom.

### ⚠ Nouveau : `manga/recuperation.py`, le filet contre un plantage

Rien n'est écrit avant `Ctrl+S`, et c'est délibéré. Mais accumuler trente planches en mémoire
pendant une heure devient normal depuis la 1.5.0 : une coupure de courant les perdait toutes.

Un miroir sous `build/<…>/manga/.recuperation/`, écrit toutes les 30 s, proposé à la
réouverture du tome.

⚠ **Hors des checkpoints, et c'est tout l'intérêt.** Écrire directement dans
`traduction_manuelle.json` aurait été plus simple — et faux : ce sont exactement les fichiers
qui **périment un rendu** (`etat_planches.SOURCES_DE_PEREMPTION`). Une planche serait passée
en « à relettrer » à chaque caractère tapé, le récapitulatif d'« Enregistrer le projet » aurait
gonflé de planches en cours de correction, et `assemble_outputs` aurait averti sur du travail
inachevé. C'est le relettrage permanent que la 1.5.0 venait de supprimer.

Le format est celui d'un checkpoint, exprès : `document.ecrire_etat`/`lire_etat` prennent déjà
un dossier quelconque. Deux sérialisations de la même chose divergeraient, et ce serait le
brouillon — celui qu'on ne relit qu'après un incident — qui divergerait en silence. État
**complet**, régions comprises : **13 à 41 ms et 2 à 11 Ko** par planche, `masks.png` inclus
(mesuré). À ce prix, économiser le PNG ne valait pas un brouillon qui ne se relit qu'à moitié.

### ⚠ Corrigé : 888 ms de fenêtre gelée à chaque ouverture, 824 ms par filtre

`etat_planche` coûte 5,9 ms — négligeable, sauf qu'on le demandait **150 fois par geste**, sur
le fil d'affichage : à l'ouverture d'un tome, à **chaque** changement de filtre, et à chaque
rafraîchissement complet de la pellicule.

    etat_planche sur tout le tome : 888 ms  (824 ms cache OS chaud — ce n'est pas du disque froid)
    avec CacheEtats, 2e passe     :  31 ms

**43×.** `manga/etat_planches.CacheEtats` mémoïse, invalidé par les `mtime` qu'`etat_planche`
lisait déjà. Le rapport de coûts est ce qui justifie le cache, et il a été mesuré avant de
l'écrire :

    les six `stat` de la signature :   13 ms   (1 %)
    le parsing JSON qu'ils evitent : 1 095 ms  (88 %)

⚠ Déporter ce calcul sur la voie de lecture aurait été la mauvaise réponse : une pastille qui
arrive 200 ms après le clic est **pire** qu'une pastille calculée tout de suite, parce qu'on
la lit pendant qu'elle est encore fausse. Le problème n'était pas la longueur du calcul mais
sa **répétition à l'identique**.

Le module vit dans `manga/` et non dans `gui/` — c'est la règle de couche que sa propre
docstring défend, et c'est ce qui le rend testable sans PySide6.

Au passage, `_item_de` balayait la liste entière à chaque appel, dans une boucle sur toutes les
planches : `rafraichir_pellicule` était en O(n²). Un index le ramène en O(n).

### ⚠ Corrigé : un relettrage de 3 planches jetait les 21 aperçus

`_sur_fin` vidait **tout** le cache dès qu'une tâche portait `planche=None` — donc après
« Enregistrer le projet » qui n'avait relettré que trois planches. Les ~21 aperçus de la
fenêtre partaient avec, soit **~29 s** de recomposition (1,37 s pièce) pour rien.

Les planches réécrites sont pourtant connues. Le vidage complet reste le repli quand la liste
ne l'est pas — un run lancé depuis l'onglet « Runs » peut toucher n'importe quoi — et
`_assembler` déclare une liste **vide**, parce qu'il relit `pages_out/` sans en réécrire une.

### Le verrou couvrait ce qu'il n'avait pas à protéger

`marquer_verrou(None, …)` faisait `setEnabled(False)` sur le panneau **entier**. Pendant
« Enregistrer le projet » — plusieurs minutes sur un gros tome — on ne pouvait plus ni
parcourir la pellicule, ni zoomer, ni **relire** ce qu'on venait de corriger. Or lire ne
risque rien : seul ce qui **écrit** doit être gelé.

Les champs passent en `setReadOnly` plutôt qu'en `setEnabled(False)` : le texte reste lisible
et sélectionnable, ce qui est précisément ce qu'on veut pouvoir faire pendant l'attente. Un
drapeau empêche la navigation de rouvrir un bouton (`_afficher_bulle` réactivait
`bouton_rendre`).

### Le zoom se reperdait à chaque planche

`_charger_planche` appelait `vue.ajuster()` sans condition. Comparer la même zone sur deux
planches consécutives — le geste de relecture par excellence — était donc impossible. Une
bascule **« Garder le zoom »** conserve le cadrage, et retombe sur l'ajustement quand la
planche suivante n'a pas les mêmes dimensions : à grossissement égal sur une planche plus
petite, on découvrirait du vide.

### Nouveau : `manga/recherche.py`, chercher dans tout le tome

Retrouver « où ai-je traduit ce nom ? » obligeait à ouvrir les planches une par une. Le champ
au-dessus de la pellicule interroge répliques, corrections manuelles et OCR japonais ; un clic
ouvre la planche et met le curseur dans la bulle.

⚠ Sur **Entrée**, pas à chaque touche : un balayage complet coûte **~210 ms** sur 150 planches.
Le coût brut de lecture n'est que de 49 ms — le reste est la validation de `checkpoints.load_*`,
qu'on ne contourne pas : une recherche qui verrait autre chose que l'éditeur serait pire que
pas de recherche.

**Défaut trouvé par son propre test** : la normalisation retirait *tous* les signes combinants,
or le **dakuten** japonais en est un. `NFD` décompose « ガ » en « カ » + dakuten, et la purge
rendait donc « カ » — chercher « ガギグ » trouvait « カキク ». On ne dépouille plus que ce dont
la base est latine. Le dakuten n'est pas un ornement : il change le son, donc le mot.

### ⚠ La suite de tests ne se terminait pas — et la cause n'était pas Ollama

Croyance de départ : « ces fichiers exigent un serveur LLM ». Le profileur dit autre chose.

    564 s au total, dont 554 s (98 %) dans onnxruntime.run — 5 appels, 110,9 s piece
      via manga/text_detection.py:101(masque_texte)

Les appels `core.power` vers Ollama, soupçonnés en premier, pèsent **8 s sur 564** — 1,4 %, et
n'apparaissent pas dans les 35 premières lignes du profil. Les corriger en croyant régler
l'affaire aurait été l'erreur exacte à éviter.

**La vraie cause** : ces tests neutralisaient le détecteur de **bulles** en pointant
`detection.model_path` sur un fichier absent, mais la passe `sfx` est délibérément **hors du
graphe d'invalidation** (`CACHE_NON_BLOQUANT`) — elle tournait donc même sur un tome dont tout
le reste est en cache, chargeait le vrai `text_detector.onnx`, et payait 110 s d'inférence CPU
par planche. Dans des tests qui ne mesurent que des **statistiques d'appels LLM**.

`tests/test_manga_lot.py` désactivait déjà `onomatopees.actif` ; quatre fixtures avaient oublié
la moitié du geste qu'elles croyaient faire.

| Fichier | Avant | Après |
|---|---|---|
| `test_manga_runtime` | 564 s | **2,25 s** |
| `test_manga_prepasse` + `test_manga_orchestrator_cache` | ne se terminaient pas | **5 s** (22 tests) |
| `test_manga_orchestrator` | > 500 s | **250 s** (vraie vision, assumée) |

Vérifié au passage, contre la croyance de départ : `test_agents` (19 s), `test_llm` (67 s),
`test_power` (6 s) et `test_manga_agents` (9 s) **passent tous** sans serveur. Ils sont lents,
pas bloqués.

### Nouveau : `pytest.ini`, des marqueurs mesurés

Le dépôt n'avait aucune configuration pytest. `modeles`, `lent`, `llm` — et
`pytest -m "not modeles and not lent"` écarte **52 tests sur 1 657**.

⚠ Un marqueur ne sert **pas** à cacher un test qui pend. Ce qui reste marqué est ce qui est
légitimement cher : de la vision par ordinateur réelle.

### Nouveau : `--check` relit `config.yaml`

963 lignes, lues par **603 `.get(...)`** à défaut silencieux : écrire
`manga.typeset.font_paht` laissait le run se dérouler entièrement avec la police par défaut,
sans un mot, et rien ne le rattrapait après coup.

    config.yaml : 1 clé(s) inconnue(s) — lues avec leur valeur par défaut, donc sans effet :
      - clé inconnue : manga.typeset.font_paht — vouliez-vous dire manga.typeset.font_path ?

⚠ **Avertit, ne refuse pas.** Refuser transformerait une config aujourd'hui acceptée en config
rejetée — soit, à la règle de ce fichier, un changement MAJEUR.

Deux décisions de forme : la référence est une liste déclarée (`core/config_schema.py`, 217
clés) parce que `config.yaml` **est** le fichier qu'on édite, donc le comparer à lui-même ne
trouverait jamais rien ; et un test la compare à l'arborescence réelle, parce qu'une référence
qui dérive produit de **faux** avertissements — pire que pas de vérification, puisqu'on cesse
alors de les lire. Le parcours s'arrête à la première clé inconnue : sans cet élagage, coller
un bloc entier sortait un avertissement par feuille et noyait le message utile.

### Code mort

`_confirmer_abandon`, `a_des_brouillons`, `_reselectionner` n'avaient plus d'appelant depuis
que `_charger_planche` a cessé de demander quoi que ce soit. Elles décrivaient un comportement
disparu — le pire genre de code mort, celui qui se lit comme une documentation.

### ⚠ `run.py` payait 5 s d'`openai` pour ne rien faire

`from pipeline.orchestrator import process_volume` en tête du module tirait `core.agents` →
`core.llm` → **`openai`**, dont l'import seul coûte **5,18 s sur 5,34** (mesuré au
`python -X importtime`). Chaque invocation le payait : `--version`, `--list`, `--check`,
`--plan`, `--diff-stages`, et surtout **`--stop`** — celle qu'on lance dans un second terminal
précisément pour arrêter vite.

`run_manga.py` importait déjà son orchestrateur dans la branche qui s'en sert ; `run.py` était
le seul à ne pas suivre ce motif. Le graphe d'import tombe de **5,34 s à ~250 ms**, dont
`core.cli` (82 ms) et `argparse` (67 ms).

⚠ Un **proxy paresseux**, et non l'import descendu dans chaque appelant : `run.process_volume`
fait partie de la surface du module et `tests/test_run_cli.py` le remplace par un double à cinq
endroits. Descendre l'import supprimait l'attribut et cassait ces cinq tests — c'est-à-dire
qu'on aurait échangé cinq secondes de démarrage contre la testabilité de l'enchaînement des
tomes. Constaté en le faisant.

⚠ `run_ocr.py` a la même forme d'import en tête mais n'a **pas** été touché : mesuré à 0,93 s,
dont l'essentiel est `numpy`, dont la brique a besoin de toute façon. Les 6 s vues au premier
essai étaient du cache froid.

⚠ Le gain **ne se voit pas au chronomètre sur cette machine** : `python -c pass` seul y a été
mesuré à 4,8 s, soit plus que `run.py --version` après correction. Le dépôt vit dans un dossier
OneDrive, et le temps mural y est du bruit. C'est pourquoi le test vérifie l'**absence
d'`openai` dans `sys.modules`** d'un sous-processus neuf — binaire, et insensible à la charge.

### ⚠ Corrigé : la sauvegarde automatique réécrivait tout, indéfiniment

`sauver_brouillons` parcourait **toutes** les planches en attente à chaque tic de 30 s et
réécrivait l'état complet de chacune, `masks.png` compris, **sur le fil d'affichage**, sans
regarder si quoi que ce soit avait bougé.

À 13-41 ms par planche, trente planches modifiées gelaient la fenêtre **0,4 à 1,2 s toutes les
demi-minutes** — et réécrivaient les mêmes octets jusqu'à la fin de la session. C'était
exactement le défaut que cette même version corrigeait ailleurs (répéter à l'identique un
travail déjà fait, sur le fil qui affiche), réintroduit dans le module qui l'accompagnait.

`recuperation.empreinte` reprend le parti de `CacheEtats` : **la clé est l'état**. Le cas
courant — on réfléchit, on ne tape pas — ne coûte plus rien.

⚠ L'empreinte porte sur le **contenu**, pas sur un `mtime` : un état vit en mémoire, il n'a pas
de date. Et les masques n'y entrent pas — plusieurs mégaoctets, les hacher coûterait plus cher
que l'écriture qu'on évite ; leurs boîtes englobantes suffisent, elles changent à chaque geste
que l'éditeur sait faire sur une région.

### ⚠ Corrigé : l'estimation de relettrage était 2,7× trop basse

`secondes = len(perimees) * 1.5` — le commentaire d'à côté disait pourtant qu'« une estimation
fausse serait pire qu'une estimation ronde ».

**469 relettrages** relevés dans les `perf.log` du dépôt (*manga A* Vol.1 à 3,
*manga C*) donnent une médiane de **3,93 s** et une moyenne de **4,00 s**, de
0,32 s à 9,25 s.

| Planches périmées | Annonçait | Coûtait |
|---|---|---|
| 5 | 8 s | ~20 s |
| 20 | 30 s | ~80 s |
| 50 | 1 min | **3 min 20** |

Cette boîte n'a qu'un rôle : dire à quoi on s'engage avant plusieurs minutes de travail
bloquant. Trois fois trop bas ne la rend pas approximative, ça la rend trompeuse.
`SECONDES_PAR_RELETTRAGE = 4.0`, avec la provenance du chiffre écrite à côté.

⚠ La valeur n'est **pas** dérivée des `perf.log` à l'exécution : le fichier peut être absent,
tronqué, ou venir d'une autre machine.

### `Reporter.close()`, et le coût des PSD enfin visible

`set_verbose_log` ouvrait `perf.log` et **rien ne le refermait** — aucun `close()` n'existait.
Sans effet en ligne de commande, où le processus se termine ; mais l'interface construit un
reporter **par run**, donc trente relettrages laissaient trente descripteurs ouverts sur le même
fichier. Sous Windows un handle ouvert **verrouille** le fichier : l'ouvrir dans un éditeur ou
l'effacer pouvait échouer sans qu'on comprenne pourquoi. Aucune donnée n'était en jeu
(`_to_log` fait `flush()` à chaque ligne) — c'est de l'hygiène de ressource.

La fenêtre ne ferme qu'une fois la voie d'écriture **au repos** : elle ne sait pas quel reporter
appartenait à quelle tâche, et plusieurs peuvent être en vol.

La ligne `[psd]` annonçait un poids sans son prix. Elle est désormais chronométrée comme
`[rendu]` juste au-dessus. Ce que la mesure disait déjà, et que le README consigne maintenant :
**8,5 Mo par planche** (469 écritures), soit **1,3 Go sur les 1,9 Go** d'un tome — **68 % de la
sortie**. Le défaut `psd_original: true` ne change pas ; un défaut assumé doit simplement être
un défaut chiffrable.

### Tests

**62 nouveaux**, aucun n'exigeant Ollama ni ne construisant de widget :
`test_manga_recuperation` (23), `test_manga_recherche` (19), `test_config_valide` (14),
`test_reporter` (+6), `test_run_cli` (+2), plus 9 sur `CacheEtats` dans
`test_manga_etat_planches`. Trois d'entre eux ont trouvé un vrai défaut avant livraison — le
dakuten, l'avertissement de config qui se démultipliait, et les cinq tests de `--all` que
l'import paresseux cassait.

---

## [1.5.0] - 2026-08-19

**L'interface cesse de se subir** — deux voies au lieu d'une, un cache d'aperçus, plusieurs
planches ouvertes à la fois, et un bouton qui enregistre le projet entier. MINEUR : aucun
cache invalidé, `only_pages` est optionnel, le bloc `gui:` est optionnel, et une ligne de
commande se comporte exactement comme avant.

### Le reproche, et sa cause

Changer de planche se payait. Lancer une retraduction sur la planche 12 empêchait de voir
la 13. Enregistrer imposait un relettrage planche par planche, puis un réassemblage à la
main. La cause était une seule et même chose : **une file unique** pour tout, où la
composition d'un aperçu attendait derrière un appel LLM.

Mesuré sur *manga A* Vol.1 (150 planches) : composer un aperçu coûte
**1,37 s** en médiane (2,67 s au pire) et pèse **1,04 Mo** ; lire le cache d'une planche coûte
**5 à 8 ms**. Tout le temps perçu était donc de la composition — et une composition se
calcule à l'avance.

### Deux voies, parce qu'elles ne protègent pas la même chose

`FilDeTravail` est unique **pour une raison** : un seul fil, donc jamais deux écritures
concurrentes sur un checkpoint. Cette raison ne vaut pas pour un aperçu, qui ne fait que lire.

- **`gui/travailleur.FilDeLecture`** — composition d'aperçus et vignettes, en parallèle de la
  voie d'écriture. ⚠ Ce n'est **pas** une file de tâches mais un **ensemble de planches
  voulues** : `vouloir()` le remplace, et le fil prend toujours la plus proche de celle qu'on
  regarde. Une file aurait grossi à chaque déplacement et aurait continué à composer des
  planches quittées depuis longtemps ; ici, se déplacer repriorise, il n'y a rien à annuler.
- **Défaut trouvé par son test** : une planche dont la composition échoue n'entre jamais au
  cache, donc reste « manquante », donc était redemandée en boucle — sur trois planches dont
  une illisible, seule l'illisible était traitée. D'où une mémoire des échecs, que
  `vouloir()` ne réarme surtout pas (il est appelé à chaque changement de planche) mais que
  `reessayer()` rouvre quand un run a pu réparer la planche.

### `gui/cache_apercu.py` — la clé fait l'invalidation

    (index, mtime de la planche nettoyée, textes affichés, mises en page)

Les textes viennent de l'état **en mémoire** du document, pas du disque : une correction non
encore enregistrée change la clé, donc invalide l'entrée **toute seule**. Il n'y a aucune
invalidation explicite à écrire — donc aucune à oublier, et c'est le mode de panne qu'on veut
éviter avant tout : un aperçu périmé montrerait un texte qui n'est plus le sien, sans rien
pour le signaler.

Plafond en **octets** (120 Mo par défaut) et non en nombre d'entrées : une planche à deux
bulles et une planche à quatorze ne coûtent pas la même chose. Préchargement en fenêtre
glissante de ±10 planches (`gui.apercu.fenetre`), soit ~21 Mo et ~27 s de fond.

**Mesuré après coup** : passer à une planche voisine déjà préchargée prend **~200 ms, calques
compris**, contre 1,4 s plus l'attente derrière la file.

### Plusieurs planches ouvertes, et un bouton pour tout écrire

`self.document` était **un** document, et changer de planche ouvrait une boîte « Enregistrer /
Abandonner / Rester ». C'est cette contrainte qui obligeait à enregistrer planche par planche.
`manga/document.py` n'a pas bougé — il était déjà par planche, avec son historique et son
contrôle de révision propres ; seul l'éditeur cesse de n'en tenir qu'un.

- La boîte de confirmation au changement de planche **disparaît** : plus rien n'est en péril.
- Le titre `[*]` parle désormais du **tome**, pas de la planche affichée.
- **« Enregistrer les modifications du projet »** (`Ctrl+Maj+S`) : écrit toutes les planches en
  attente, relettre **les seules planches périmées** en **un** `process_volume`, puis
  réassemble **une** fois. Un récapitulatif annonce d'abord les planches, leurs motifs et le
  temps estimé — engager plusieurs minutes sans le dire serait le défaut qu'on corrige.
- Une planche refusée (un run l'a réécrite entre-temps) est **nommée, son travail conservé, et
  n'arrête pas les autres** : abandonner neuf planches parce que la dixième a bougé serait le
  pire des retours.

### Corrigé : une correction manuelle ne périmait aucun rendu

`_pages_perimees` ne comparait `pages_out/` qu'à `traduction.json`. Or l'éditeur n'écrit
**jamais** là : une réplique corrigée à la main va dans `traduction_manuelle.json`, un bloc
déplacé dans `mise_en_page.json` — et c'est précisément ce qui les fait survivre à un
`--from traduction`. Ces travaux ne périmaient donc **rien**, ni pour l'avertissement
d'`assemble_outputs`, ni pour le nouveau bouton qui en dépend entièrement : l'archive
continuait d'embarquer l'ancienne image sans un mot.

**`manga/etat_planches.py`** (nouveau, sans Qt) porte désormais la règle, élargie à
`traduction_manuelle.json`, `mise_en_page.json` et `regions.json`. La même question se posait
dans l'orchestrateur et dans l'interface ; deux réponses auraient fini par diverger sur ce qui
compte comme « modifié ».

### Corrigé : « Appliquer » gelait tout l'éditeur

`Fenetre._relettrer` soumettait `Tache(planche=None)`, ce qui déclare « je touche tout le
tome » — alors que `only_page` garantit le contraire. Relettrer une planche grisait donc
l'éditeur entier.

### `only_pages`, et une logique de bornes enfin testable

`process_volume` accepte un **ensemble** de planches, à côté de `only_page`. Les deux se
composent par **intersection** : `--page` ne peut qu'affiner une sélection, jamais l'élargir.

La logique de bornes vivait en ligne dans `process_volume`, donc n'était vérifiable qu'en
faisant tourner un orchestrateur complet, avec ses modèles et son serveur LLM. Elle est
extraite en `cibles_de_run`, fonction pure, et le cas qu'elle protège est verrouillé :
`--page 999` ne traitait rien mais allait quand même au bout, réécrivant `RAPPORT.md` et
réencodant le CBZ — une faute de frappe passait pour un run réussi.

### La pellicule de vignettes

**`gui/pellicule.py`** — la liste `12   page_0012.png` devient une bande de vignettes avec
pastilles : `⟳` rendu périmé, `✎n` répliques corrigées, `↔n` textes déplacés, `⚠n`
débordements, `∅` aucune détection. Un filtre isole *modifiées à la main · rendu périmé ·
débordements · sans traduction · jamais rendues*.

Vignettes en cache **disque** sous `build/<…>/manga/.vignettes/` (dossier caché : contrairement
à `pages_clean/`, il n'est fait pour être lu par personne), produites dans la voie de lecture,
et repérimées dès qu'un relettrage réécrit la planche — une vignette figée montrerait
l'ancienne image, exactement ce qu'on regarde pour vérifier son travail. C'est l'emprunt
assumé à *Koharu* : reconnaître une planche à l'œil est ce qui rend un tome navigable.

⚠ Deux portées délibérément différentes : les **aperçus** ne couvrent que la fenêtre (bornés en
mémoire), les **vignettes** couvrent tout le tome (sur disque, une fois).

### Les commandes opaques

| Avant | Après |
|---|---|
| « Enregistrer », presque toujours grisé | **« Enregistrer la planche »** + une ligne d'état qui dit *pourquoi* : `Planche 12 · 6 bulles · 2 corrigées · rendu périmé · rien à enregistrer` |
| « Ajuster », sans effet visible | groupe **`[−] [ 46 % ] [+] [Ajuster (F)]`** — il fonctionnait, mais `_charger_planche` ajuste déjà, et rien n'affichait le grossissement |
| « Voir le rendu final », lent au retour | **« Comparer au rendu du pipeline »**, bascule instantanée grâce au cache |

Deux boutons promettaient une écriture (« Enregistrer » et « Garder ma version »), dont l'un
presque toujours grisé : le grisé n'était pas un défaut mais l'absence de modification, que
rien n'annonçait.

### Confort

- `Page préc.`/`Page suiv.` entre planches (jamais pendant une saisie : la touche appartient
  alors au champ), `F` ajuster, `Échap` revenir à l'outil « Choisir », `Ctrl+J` journal.
- **Double-clic sur une bulle** → curseur dans sa réplique. Il fallait viser la liste de
  droite pour éditer ce qu'on regarde à gauche.
- **Journal replié** par défaut — il occupait 220 px en permanence pour un contenu qu'on ne
  lit qu'après un incident — et **déplié tout seul au premier avertissement**.
- Avancement du préchargement dans la barre du haut, effacé dès qu'un run parle : écraser la
  progression d'un run ferait perdre de vue ce qui compte.

### Documentation

**`COMMANDES.md`** — toutes les commandes des trois briques, une ligne chacune, plus les
raccourcis de l'interface. Le README fait 1 740 lignes et n'était plus consultable pour
retrouver une option ; il garde le *pourquoi*, le mémo donne le *comment*. Les 48 commandes
qu'il documente ont été vérifiées contre l'`--help` des trois points d'entrée.

### Tests

53 nouveaux, aucun n'exige Ollama ni ne construit de widget : `test_manga_etat_planches` (15),
`test_gui_pellicule` (21), `test_gui_cache_apercu` (17), `test_gui_lecture` (15),
`test_manga_cibles_run` (16). La logique métier reste hors de `gui/`, donc l'essentiel se teste
sans PySide6.

---

## [1.4.0] - 2026-08-18

**La brique SCAN** — un light novel japonais livré en images de pages devient un `.md` que le
pipeline LN lit sans rien changer. MINEUR : rien n'est cassé, aucun cache existant n'est
invalidé, le bloc `scan:` de `config.yaml` est entièrement optionnel, et le seul changement
hors de la nouvelle brique est la réparation d'un défaut qui existait déjà.

### Pourquoi

`sources/<Projet>/<Tome>/JAP/` peut ne contenir que des `.jpg`. `pipeline/sources.py:123-127`
ne retenant que `.docx|.pdf|.epub|.txt|.md`, le tome s'arrêtait sur « Aucune source
exploitable ». Il fallait donc produire du texte à partir des pages.

### La mesure qui décide de toute l'architecture

`manga-ocr` redimensionne son entrée en 224 × 224. Sur une page réelle de 2 452 × 3 543 px,
une **colonne entière** de ~40 caractères (2 733 px de haut) en ressort *inventée* — 23 à 29
caractères rendus, sans rapport avec la page. Les mêmes pixels découpés en tranches de 8 à 16
caractères sont lus correctement à ~95 %.

Toute la brique existe donc pour répondre à une seule question — **où couper ?** — et elle y
répond **sans le moindre modèle** : une page de roman imprimé est une grille régulière, et une
grille se mesure. C'est le raisonnement que `manga/ocr.py` tient déjà pour l'ordre de lecture.

### `scan/grille.py` — l'analyse, et les falaises qu'elle évite

- **Le seuil de binarisation n'est pas un réglage, c'est une falaise.** À `< 200`, le halo
  JPEG donne 17 px d'encre par colonne d'image : il ne reste **aucune** gouttière et la page
  sort en UNE bande. À `< 112` elle sort en 16 colonnes régulières. Aucune valeur fixe n'étant
  sûre d'un tirage à l'autre, le seuil est **choisi par balayage** (6 valeurs, 63 ms/page) sur
  la régularité de la grille obtenue. ⚠ Otsu est explicitement écarté : sur un histogramme
  écrasé sur le blanc (médiane 255) il place le seuil à ~195, soit très au-delà de la falaise
  — mesuré, il rendait deux pages sur cinq en une seule colonne.
- **Une bande brute n'est pas une colonne** : un `「` ou un `ー` coupe sa propre bande — 41
  bandes pour 16 colonnes réelles. D'où une fusion à écart **relatif**.
- **L'indentation ne se lit pas sur le haut d'encre brut.** Il varie de ±20 px selon le
  premier glyphe. Le haut du corps est donc le **mode** des débuts de colonne, jamais leur
  minimum : sur la page mesurée, le minimum classait douze colonnes sur seize comme
  indentées, le mode en retient quatre — exactement les ouvertures de paragraphe.
- **Le numéro de page a deux visages.** Isolé en marge sur une page impaire ; posé **au-dessus
  d'une colonne**, dans les mêmes abscisses, sur une page paire — la règle de marge n'y voit
  alors rien, et l'OCR lisait le numéro à la suite du texte. D'où un second filet, l'élagage
  des extrémités. ⚠ Avec un critère de position, sans quoi il mangeait les crochets fermants
  isolés derrière un long tiret (constaté, corrigé, verrouillé par un test).
- **Une coupe ne tombe jamais sur de l'encre.** C'est LA propriété du module : couper dans un
  glyphe en donne la moitié à chaque tranche et le modèle en invente un entier de part et
  d'autre — origine exacte des doublons de couture mesurés. La coupe est **proportionnelle**
  puis ramenée sur une gouttière **large** (≥ 0,15 × pas : les fines séparent les traits d'un
  même signe — 143 gouttières relevées sur une seule colonne de 44 caractères).

### `scan/lecture.py` — un garde-fou qui ne coûte rien

La grille prédit combien de caractères une colonne contient, l'OCR rend une chaîne : les
comparer attrape le mode d'échec ci-dessus. Une colonne trop éloignée est **relue une fois,
avec un découpage décalé** — rejouer le même découpage redonnerait la même hallucination, le
modèle étant déterministe.

⚠ Le seuil est large (25 %) et c'est assumé : `cases` surestime d'environ 7 % (le pas mesure
la largeur d'encre, pas l'avance typographique). J'ai cherché l'avance réelle en ajustant les
hauteurs de colonnes sur des multiples entiers ; sur cinq pages elle ressort entre 0,92 et
1,33 fois la largeur médiane, pour un résidu à peine meilleur que le hasard. L'estimateur ne
tient pas, et une calibration fragile serait pire qu'un seuil large.

Lecture par lots de 16 : 0,488 s/tranche contre 0,655 s une par une, **sortie identique au
caractère près** (un test le verrouille).

### `scan/assemblage.py` — le document

Les paragraphes **traversent les pages** ; un roman haché tous les quarante caractères
fausserait le découpage en blocs du pipeline LN de bout en bout. Deux signaux d'ouverture,
réunis par un OU et complémentaires : l'indentation (récit) et le **crochet ouvrant**
(réplique — en typographie japonaise elle n'est pas indentée, le crochet occupe le retrait,
et la règle géométrique ne peut donc pas la voir).

Une page sans grille exploitable devient `<!-- IMG: media/page_0010.jpg -->` — le marqueur que
`extract.py` produit déjà pour les `.docx`/`.epub`, donc les illustrations ressortent **à leur
place** dans le rendu final. Une page à gros corps tenant en 3 colonnes devient un titre `#`,
ce qui suffit à `pipeline/split.py`. Les furigana sont ignorés par défaut — même arbitrage
mesuré que `decoupage.epub.ruby`, où les conserver gonflait le japonais de 30 %.

### Corrigé : un `.md` ne pouvait pas porter d'images

`pipeline/extract.py` rendait le texte seul pour `.txt|.md`. Un marqueur `<!-- IMG: … -->` y
survivait donc sans que le fichier ne soit jamais copié dans `media_dir`, et comme `render.py`
appelle Pandoc avec `--resource-path .` depuis le build, l'image sortait **manquante, en
silence**. La branche copie désormais les images désignées (chemins résolus relativement au
document) et les remonte dans `Extracted.images`. Le défaut valait pour tout `.md` écrit à la
main. `Extracted` gagne un champ `avertissements`, remonté aux avertissements du plan de tome
— là où l'utilisateur les lit déjà.

### Divers

- **Deux passes, pas une boucle.** Le verdict « page de titre » compare le pas de la page au
  pas médian du **tome** ; en une seule passe il aurait dépendu des pages déjà vues, et
  `--page 12` n'aurait pas donné le même résultat qu'un tome entier. L'analyse coûte 0,1 s
  contre 30 s de lecture : la faire d'abord en entier ne coûte rien et rend le verdict
  déterministe.
- **Le `.md` est écrit dans `sources/`** — seule écriture du dépôt à cet endroit, et
  délibérée : c'est le seul endroit où `pipeline/sources.py` regarde, le fichier se corrige à
  la main, et il survit à un vidage de `build/`.
- **Un tome incomplet n'écrit pas de document.** Un `.md` tronqué en silence partirait en
  traduction amputé sans que rien ne le dise.
- **Cache par page**, arrêt propre par le fichier `STOP` de `core.control` (unité d'arrêt : la
  page), `RAPPORT.md` classé **par doute** — personne ne relira 270 pages de japonais vertical
  à l'œil.
- `run_ocr.py --apercu` écrit une image de contrôle de l'analyse sans charger de modèle
  (~0,1 s), sur le modèle de `tools/apercu_detection.py`.
- `requirements-scan.txt` : sous-ensemble strict de `requirements-manga.txt`. **Pas**
  d'`onnxruntime` — la brique ne détecte rien par réseau de neurones.
- 97 tests, aucun ne charge de modèle : le lecteur est injecté dans `process_volume`.

⚠ **Coût honnête** : ~0,5 s par tranche, ~30 s par page, **~2 h pour un tome de 270 pages**
sur processeur. C'est une passe unique et reprenable, mais c'est une passe longue.

---

## [1.3.0] - 2026-08-18

**L'éditeur dynamique** — la mise en page devient une donnée, le texte se déplace, et rien ne
s'écrit avant `Ctrl+S`. MINEUR : rien n'est cassé, aucun cache n'est invalidé, et une planche
sans `mise_en_page.json` est lettrée exactement comme avant.

### La position du texte devient une donnée

Elle n'existait **nulle part** : `typeset_page` la recalculait à chaque rendu depuis le masque
de la bulle, et `fits_out` — la seule trace — n'était même alloué que si l'export PSD était
actif, puis jeté. Déplacer un bloc de texte était donc impossible par construction : il n'y
avait rien à déplacer.

- **`mise_en_page.json`** — même patron que `traduction_manuelle.json` : fichier séparé, jamais
  écrit par le pipeline, tolérant à un contenu abîmé, `{}` supprime. Ajouté à
  `projet._SUIVIS`, sans quoi un déplacement ne ferait pas bouger la révision et le contrôle
  de fraîcheur ne verrait rien passer.
- **`typeset_page(layouts=…)`** impose le rectangle et le corps au lieu de les chercher. Le
  rectangle enregistré devient **aussi le masque de découpe** (`typeset.style_impose`) : sans
  cela, `calque_fit` rognerait un texte déplacé à l'ancienne forme de sa bulle et il
  disparaîtrait en silence — le pire mode d'échec possible pour un éditeur.
- L'harmonisation de planche **épargne les tailles choisies à la main** (`Fit.impose`). Ramener
  les bulles trop grandes vers la médiane est un bon réflexe automatique et une trahison quand
  quelqu'un a posé une taille.
- Un rectangle devenu trop petit fait **retomber sur la recherche normale** : une mise en page
  enregistrée est une préférence forte, pas une consigne suicide.

### L'éditeur part de la planche nettoyée

Il affichait `pages_out/`, c'est-à-dire une image aplatie où le texte est cuit dans les pixels.
Le fond est désormais `pages_clean/`, et chaque réplique est un **calque RGBA distinct** produit
par `typeset.calque_fit` — la fonction même du rendu final.

Mesuré sur *manga A* Vol.1 planche 6 : **0 pixel d'écart sur 1 800 000** entre
l'aperçu en calques et le `pages_out/` écrit par le pipeline. L'aperçu n'est pas une
approximation, c'est le rendu décomposé.

Glisser un bloc le translate (instantané, aucun recalcul) ; le ré-habillage n'intervient qu'au
dépôt. Un bouton bascule vers le rendu final, parce que comparer reste utile. La composition
tourne dans la file : elle exige le scan d'origine, dont l'obtention peut extraire un CBZ.

### Un seul chemin de rendu

**`manga/rendu.py`** — l'orchestrateur et l'éditeur passent par la même fonction. Écrire un
second moteur pour l'aperçu aurait été le pire des deux mondes : deux chemins libres de diverger
sur la seule chose que l'utilisateur regarde vraiment. Un test interdit à `process_volume` de
rappeler `typeset_page` en direct.

### Un vrai document, avec Enregistrer

**`manga/document.py`** — l'état d'une planche vit en mémoire et **rien n'est écrit avant
`Ctrl+S`**. Chaque geste était jusqu'ici une écriture immédiate : honnête, sans surprise, et
incompatible avec ce qu'on attend d'un éditeur — hésiter, essayer, revenir en arrière.

- **Historique par instantanés, pas par inverses.** Le plan prévoyait d'empiler l'opération
  inverse ; c'est économique en mémoire et fragile — l'inverse d'une scission qui a réordonné
  la planche et reporté des textes par IoU n'a rien d'évident, et un inverse faux corrompt
  silencieusement un cache qu'on croit intact. Les instantanés **partagent les masques par
  référence**, en s'appuyant sur une propriété que le code tient déjà : aucun masque n'est
  jamais muté en place. Coût : quelques kilo-octets par pas, au lieu de ~30 Mo.
- **Le cœur pur est partagé** avec `manga/edition.py` (`document.poser_regions`) : réordon­nan­ce­ment,
  appariement par IoU, report de l'OCR, de la traduction, des corrections manuelles, des
  origines **et des mises en page**. Deux implémentations de « qu'est-ce qui est conservé,
  qu'est-ce qui est perdu » finiraient par diverger, et celle-ci décide du sort de traductions
  déjà payées.
- **L'enregistrement vérifie la révision** de `projet.json` : un run qui a retouché la planche
  pendant la session fait refuser l'écriture — et **conserve** la modification — plutôt
  qu'écraser.
- `masks.png` n'est réécrit que si les **régions** ont changé. C'est le seul écrit coûteux du
  lot (un PNG pleine page) et corriger une réplique ne doit pas le payer.
- Titre marqué `[*]`, confirmation à trois issues au changement de planche et à la fermeture —
  **« Enregistrer » en premier**, parce que perdre du travail parce qu'on a changé de planche
  est le pire des retours. Les brouillons de saisie sont versés dans le document avant
  l'écriture : une réplique tapée puis enregistrée sans repasser par « Garder ma version » ne
  se perd pas.

---

## [1.2.0] - 2026-08-18

**De l'éditeur qui fige à l'éditeur qui édite.** MINEUR : rien n'est cassé, aucun cache n'est
invalidé. Une seule valeur de `config.yaml` change — et elle était **fausse** (cf. `num_ctx`).

L'interface livrée en 1.1.0 a été utilisée pour de vrai, et l'usage a produit une liste de
défauts précis. Trois d'entre eux étaient des **contradictions entre le code et sa propre
documentation**.

### Le défaut le plus visible : le français par-dessus le japonais

`edition.ajouter_zone` ne touchait jamais `pages_clean/`, et **aucune** des étapes de reprise
proposées par l'éditeur ne relance le nettoyage — `downstream("rendu")` vaut `{"rendu"}`. Le
lettrage recomposait donc sur une planche où la nouvelle zone n'avait jamais été vidée.

Toute opération de zone repeint désormais la planche nettoyée (`edition.repeindre_clean`), en
mesurant le style sur le **scan d'origine** et en peignant sur la planche nettoyée — c'est
précisément ce que le mot-clé `styles=` de `clean_bubbles` existait pour permettre. Symétrie :
supprimer une fausse détection **restaure le dessin d'origine** sous la zone retirée, au lieu
de laisser un aplat blanc définitif. Et un bouton unique enchaîne **vider, lire, traduire**
(`edition.reprendre_zone`).

### L'interface ne fige plus

- **Une file d'attente et un fil unique** (`gui/travailleur.py`). Les éditions de zone étaient
  synchrones sur le fil d'affichage — masques numpy pleine page, quatre fichiers réécrits — et
  le premier clic sur « Relire » déclenchait `scan_volume`, donc l'extraction d'un CBZ entier.
- **Le verrou est par PLANCHE**, plus global : relire une bulle de la planche 12 n'empêche plus
  d'éditer la 30. Une seconde demande sur une planche occupée est **mise en file**, jamais
  refusée par une boîte de dialogue — refuser un geste que l'utilisateur vient de faire est le
  pire des retours.
- **Les trois trous de concurrence sont fermés** : un seul point d'entrée (`soumettre`), et un
  seul objet de signaux créé une fois — au lieu d'être réassigné sous le fil précédent, qui
  continuait d'émettre vers un objet que plus personne n'écoutait.

### Les modèles restent chauds

**`manga/services.py`** — extraction de la closure `_lazy` de `process_volume`, avec une durée
de vie que l'appelant choisit : la CLI en crée un par run, l'interface un par fenêtre. Chaque
clic sur « Retraduire » reconstruisait jusqu'ici les agents, relisait les prompts **et
rechargeait le glossaire YAML**, sans `runtime.wire_reporter` — les incidents LLM partaient
donc sur `stdout`, c'est-à-dire nulle part dans une interface graphique.

**`process_volume(passes_volume=False)`** — saute le relevé terminologique, le dédoublonnage du
glossariste et la fiche de contexte quand l'éditeur relance UNE planche. Ces trois passes
raisonnent à l'échelle du tome ; les rejouer pour une bulle est du temps pur.

### Le journal, et ce que le rapport taisait

- **`perf.log` existe enfin pour un run lancé à l'écran.** `set_verbose_log` n'était appelé
  nulle part depuis `gui/` : `Reporter._to_log` teste `getattr(self, "_vlog", None)` et sautait
  donc **toutes** les écritures en silence, pendant que les docstrings affirmaient le
  contraire. Le lanceur porte une case « verbose », sans laquelle le canal verbose reste vide
  par construction.
- **`qa.json` gagne `origine`** (`pipeline` | `editeur` | `manuelle`) **et `think`**. Une
  réplique reprise à la main était indétectable — `rattrapee: false` comme les 943 autres — et
  `--think` ne laissait aucune trace nulle part, si bien que deux runs d'un même tome, l'un
  raisonné et l'autre non, étaient incomparables.
- **Une planche sans `qa.json` est NOMMÉE.** Le rapport annonçait « 149 analysée(s) sur 150 »
  sans jamais citer la manquante : ses bulles échappaient à tout contrôle qualité en silence.
- **Le CBZ signale les rendus périmés** — une page dont `pages_out/` est plus ancien que sa
  traduction. C'est le défaut de la page 52 du Vol.4 : l'archive livrée portait une planche
  désynchronisée de son texte.
- **Trois correctifs d'affichage** : l'ellipse n'est ajoutée que si la chaîne est réellement
  tronquée (le rapport écrivait `« Dok...… »` sur des répliques entières, ce qui se lit comme
  une troncature du lettrage) ; les traductions SFX sont coupées avec un marqueur ; les
  compteurs de triage sont relus depuis **tous** les `qa.json` au lieu de ne décrire que le
  dernier run (« 3 traduite(s) » pour 338 réellement traduites).

### La mesure qui commandait tout le reste

**`llm.num_ctx` passe de 65 536 à 32 768** — la valeur déclarée était le **double** de la
réalité. `quality_manga.place_disponible` croyait donc disposer de 55 705 tokens utiles quand
le plafond réel est 27 852. Et Ollama ne dégrade pas progressivement : mesuré sur ce serveur,
un prompt de 31 398 tokens passe entier, un prompt de ~33 200 est **silencieusement ramené à
16 386** — plus de la moitié du contexte jetée, sans erreur ni avertissement. Un lot de 20
planches avec raisonnement débordait donc sans un mot, et le défaut n'apparaissait qu'au
rapport, sous forme de planches vides.

Une valeur déclarative fausse étant pire qu'absente, elle est désormais **vérifiée** : au
premier appel de traduction, elle est comparée à ce que rend `/api/ps`, et un écart est signalé
au journal (`core.power.contexte_charge`).

### Un lot interrompu ne perd plus tout

Les traductions d'un lot sont écrites **dès leur réception**, planche par planche. La 1.1.0 les
gardait en mémoire pour préserver un invariant réel — `traduction.json` en cache est toujours
déjà passé par le rattrapage unitaire, et c'est sur quoi compte la reprise. Le coût a été
mesuré sur le Vol.4 : un `--lot 20` interrompu a produit **une** planche en 44 minutes, et le
tome a dû être retraduit en entier à `lot=1`.

La bonne réponse n'était pas de choisir entre les deux, mais de **rattraper tout de suite** :
le rattrapage est un appel court par bulle vide, plafonné à 3 par planche, et il n'a besoin que
des bbox — que le lot transporte déjà. L'invariant tient, et l'unité de perte redescend à la
planche.

`RAPPORT.md` dit maintenant la taille de lot et le raisonnement réellement employés, relus
depuis les `qa.json` — donc à l'échelle du tome et non du dernier run.

### La saisie ne se perd plus

Changer de bulle écrasait le champ de traduction sans un mot. Les modifications non
enregistrées sont retenues dans des **brouillons** : elles survivent à la navigation, la liste
les marque d'un `●`, et changer de planche demande confirmation. Rien n'est écrit sur disque
sans un geste explicite.

---

## Note — l'interface graphique, livrée en 1.1.0 mais non numérotée

**L'interface graphique, et la retouche directe d'une planche.** C'est ce que le README
annonce depuis la 1.0.0 : *« 2.0.0 — interface graphique et édition directe. L'objectif est de
retoucher une planche sans passer par Photoshop. »*

⚠ **Livré, mais pas encore numéroté.** La version reste **1.1.0** : la 2.0.0 est une promesse
écrite, et la poser demande d'avoir réellement retouché des planches à l'écran, pas seulement
d'avoir livré le code. Le passage à 2.0.0 se fera au vu de cet usage — ce sera un MAJEUR *par
exception*, comme la 1.0.0 : rien n'est cassé, aucun cache n'est invalidé, aucune clé de
`config.yaml` n'est retirée, et `run.py` / `run_manga.py` / `app.py` fonctionnent à
l'identique, sans PySide6 installé.

En attendant, tout ce qui suit est utilisable dès maintenant.

### Ce qui devient possible

```
pip install -r requirements-gui.txt
python gui.py
```

- **Voir** les zones de bulles superposées à la planche, **avec leur numéro d'ordre de
  lecture**. C'est l'information la plus utile de tout l'écran : cet ordre est ce qui aligne
  `ocr.json` et `traduction.json`, et une inversion est parfaitement invisible sur la page
  rendue. Les bulles vides et celles reprises à la main ont leur couleur.
- **Corriger une zone** que la détection a manquée, mal découpée ou inventée : ajouter
  (rectangle ou ellipse), redessiner, supprimer, **scinder** par un trait de coupe.
- **Retoucher une réplique** au clavier ; **relire** une bulle à l'OCR ; **retraduire** une
  bulle par un appel court.
- **Lancer un run** manga *ou* light novel, avec journal en direct, barre de progression et
  arrêt propre — y compris les réglages de lot et de raisonnement de la 1.1.0.
- **Relettrer** la planche d'un bouton, et voir le résultat.

### La règle d'architecture

**`gui/` ne contient que du Qt.** Toute la logique métier est en Python nu dans `manga/`, et
se teste sans que PySide6 soit installé :

- **`manga/edition.py`** — le seul écrivain de `regions.json` hors pipeline ;
- **`manga/traduction_unitaire.py`** — le prompt « une bulle, une réponse », **extrait** de
  `_rattraper_bulles` et désormais partagé avec l'interface. Deux copies d'un prompt qui
  porte trois garde-fous seraient deux jumelles libres de diverger ; un test tombe si le
  rattrapage se refait la sienne.

L'interface n'a **aucun chemin de traitement qui lui soit propre**. Elle appelle
`process_volume` (les deux briques), écrit le fichier `STOP` par `control.request_stop` — le
même mécanisme que `--stop` —, et relettre par `process_volume(only_page=N,
restart_from="rendu")`. Un tome retouché à l'écran se relance à l'identique avec
`run_manga.py`, et réciproquement.

### Le point dur : corriger une bulle ne doit pas coûter les autres

Le réflexe du pipeline devant un changement du nombre de régions est
`checkpoints.invalider_textes`, qui supprime OCR et traduction de **toute** la planche. C'est
juste pour une re-détection, où plus rien ne correspond. Ce serait ruineux ici : ajouter une
bulle oubliée sur une planche qui en compte sept jetterait les six autres — six traductions
déjà payées, et les corrections manuelles avec.

`manga/edition.py` fait donc un **appariement par IoU** entre l'ancien et le nouveau jeu de
régions (`detection_retry.apparier`, déjà écrit pour l'arbitrage de re-détection). Ce qui est
resté la même bulle garde son OCR, sa traduction **et sa correction manuelle**, même quand
l'ordre de lecture change — les clés de `traduction_manuelle.json` sont des index de bulle, et
sont remappées ; sans cela, une réplique écrite à la main pointerait la mauvaise bulle dès
qu'on ajoute une zone en tête de planche.

Deux invariants sont verrouillés par des tests : l'ordre de lecture est recalculé à chaque
opération (`ocr.reading_order`), et les masques sont rendus **disjoints** — `masks.png` est
une image d'étiquettes, deux masques qui se recouvrent verraient le second effacer le premier
au rechargement, silencieusement.

### Ajouté

- `gui.py` + `gui/` (fenêtre, éditeur, canevas, lanceur, worker) ; `requirements-gui.txt`
  (`PySide6>=6.7`), **séparé** comme `requirements-manga.txt` : ~120 Mo qu'un utilisateur de
  la ligne de commande n'a pas à payer.
- `manga/edition.py` — `ajouter_zone`, `modifier_zone`, `supprimer_zone`, `scinder_zone`,
  `relire_zone`, `retraduire_zone`.
- `manga/traduction_unitaire.py` — `prompt_bulle`, `traduire_bulle`.
- `checkpoints.save_traduction_manuelle` — le seul écrivain de `traduction_manuelle.json`,
  **jamais appelé par le pipeline** ; un dictionnaire vide supprime le fichier plutôt que
  d'écrire `{}`, pour que « aucune correction » et « fichier vide » se lisent pareil.
- `checkpoints.taille_image` — la taille de planche vue par la détection, sans rouvrir
  l'image.
- `quality_manga.LIBELLES_RATTRAPAGE["source_vide"]` — le rattrapage écarte ces bulles en
  amont et ne le voyait jamais ; l'interface, elle, peut recevoir un clic « retraduire » sur
  n'importe quelle bulle et doit pouvoir dire pourquoi elle n'a rien fait.

### Ce que l'interface ne fait pas, délibérément

- **Elle ne réécrit jamais `config.yaml`.** Ses 800 lignes de commentaires en sont la
  documentation ; un aller-retour `yaml.safe_dump` les effacerait toutes. Les réglages d'un
  run sont des mutations du dictionnaire en mémoire, exactement comme les drapeaux des CLI. Le
  menu propose d'ouvrir le fichier dans l'éditeur système.
- **Elle ne dessine rien sur la planche.** Le principe « l'IA ne dessine jamais » vaut aussi
  pour l'utilisateur : on édite des zones et du texte, le nettoyage et le lettrage restent
  déterministes et appartiennent au pipeline.
- **Un seul run à la fois**, et l'édition est suspendue pendant. Deux `process_volume` sur le
  même tome se disputeraient les mêmes checkpoints, et le second effacerait le `STOP` du
  premier.

### Concurrence

`projet.json` porte depuis la 1.0.0 une **révision** qui n'augmente que si le contenu change.
Elle est retenue à l'ouverture d'une planche et revérifiée avant chaque écriture : un run qui
aurait retouché la planche pendant qu'elle est à l'écran fait refuser l'écriture, avec
proposition de recharger. C'est l'`expected_revision` que la docstring de `manga/projet.py`
annonçait.

`core.control.install_sigint` ne fait rien hors du fil principal — c'est ce qui rend sûr
l'appel de `process_volume` depuis un `QThread`, et c'est aussi pourquoi le fichier `STOP` est
le seul chemin d'arrêt de l'interface.

---

## [1.1.0] - 2026-08-17

**Une planche cesse d'être l'unité d'appel.** MINEUR : nouvelle clé optionnelle à défaut
iso-comportement (`manga.lot.planches: 1` = la 1.0.0 au bit près), deux nouveaux drapeaux, et
une réécriture de `prompts/manga_traducteur.md` qui n'ajoute qu'une section — le contrat de
sortie d'une planche seule est inchangé.

### Ce qui débloque le lot

Le report du CHANGELOG 1.0.0 nommait trois exigences : *« un `bubbles_cap` proportionné, la
re-répartition des répliques vers les bonnes planches, et l'unité d'arrêt propre qui passe de 1
à 20 planches »*. Les deux premières sont livrées ici ; la troisième est un **coût assumé et
documenté**, pas un problème résolu.

Le mur matériel, lui, a bougé : le `num_ctx` du Modelfile passe de 32 768 à **65 536**. C'est
ce qui rend l'arbitrage jouable — mais seul le premier des deux arguments qui avaient fait
écarter le tome-en-un-appel tombe. Le second reste entier : *un seul numéro manquant sur 815
relancerait les 815*. D'où un lot **borné à 20 planches** et un repli **par planche**.

### Ajouté

- **`manga.lot`** — traduction de plusieurs planches consécutives en un seul appel.
  `planches: 1` par défaut (aucun changement), jusqu'à 20. Sur un tome de 131 planches,
  `--lot 20` fait **7 appels au lieu de 131** : le prefill du glossaire, de la fiche de
  contexte et du prompt système n'est plus payé qu'une fois par lot.
- **`--lot N`** et **`--think [NIVEAU]`** sur `run_manga.py`. Les deux écrivent dans le
  `config` plutôt que d'être passés à `process_volume` : c'est ce qui les rendra disponibles à
  l'identique à l'interface graphique, qui n'appellera pas la CLI.
- **`manga.lot.think` / `thinking_budget`** — le raisonnement du traducteur, appliqué à
  `manga.modeles.manga_traducteur` **seul** (pas au terminologue ni aux onomatopées, dont le
  coût n'a pas à suivre la taille du lot). Le raisonnement était mesuré inutilisable à une
  planche par appel (~1 h 15 à 2 h 50 par tome) : c'est le lot qui le rend abordable, la trace
  étant payée une fois par lot au lieu d'une fois par planche. Le budget par défaut est 2 500
  et non les 16 000 de la racine, dimensionnés pour un bloc de light novel.
- **`llm.num_ctx`** — déclaratif, jamais envoyé (il vit dans le Modelfile Ollama, et l'endpoint
  `/v1` ne l'accepte pas). Sert à ce que les garde-fous **calculent** si un prompt tient au lieu
  de le supposer : `quality_manga.place_disponible` refait à chaque lot le calcul qui n'avait
  été fait qu'une fois, à la main.
- **`qa.json` gagne `lot_taille`** — le nombre de planches qui partageaient l'appel, ramené à 1
  pour une planche repliée. Sans lui, un tome traduit par lots et un tome traduit planche par
  planche sont indistinguables au rapport, y compris pour comparer deux runs. `RAPPORT.md`
  gagne la ligne correspondante.

### Comment le lot reste sûr

**La numérotation reste PLATE** (1..N sur tout le lot, les planches n'étant que des
séparateurs). C'est le choix qui coûte le moins en risque : `analyser_numerotation`,
`repliques_par_bulle`, `sans_prefixe` et les six motifs de `quality_manga` lisent exactement la
forme qu'ils lisent depuis la 0.24.0 — seule la longueur change. Une numérotation à deux
niveaux (« 3.2 ») aurait demandé une seconde expression régulière, c'est-à-dire une jumelle
libre de diverger de celle qui décide du retry.

**Un lot n'est jamais retenté en entier** — ce serait annuler son gain pour une seule planche
fautive. Deux replis, tous deux vers le chemin de la 1.0.0 :

- **le lot entier**, si le modèle n'a numéroté aucune ligne (reconstruction positionnelle) :
  rattacher 130 répliques à leurs bulles par leur seul ordre est indéfendable ;
- **une planche**, s'il lui manque une réplique dont la source **porte du texte**. Le test
  passe par `source_rattrapable` et non par « la tranche est pleine » : une bulle dont l'OCR
  vaut `（）` est vide à raison, et refaire une planche entière pour elle serait un appel payé
  pour rien — que le rattrapage unitaire refuserait de toute façon ensuite.

Au pire, on retombe donc sur le coût **et** le résultat de la 1.0.0, planche par planche.

**Aucune signature de découpage**, contrairement au light novel. `_sceller_decoupage` existe
côté LN parce que ses caches sont **par bloc** ; ici les résultats restent écrits par planche,
alignés sur les bulles de cette planche. Changer la taille du lot entre deux runs ne peut donc
désaligner personne — et y ajouter une signature ferait retraduire un tome entier pour rien.
`tests/test_manga_lot.py` verrouille cet invariant.

### Ce que le lot coûte

- **L'unité d'arrêt propre ET l'unité de perte passent de 1 à `planches`.** Un `--stop` ou une
  panne en milieu de lot fait reperdre le lot entier. Les traductions d'un lot ne sont
  délibérément **pas** écrites à leur réception : `traduction.json` en cache est, depuis
  toujours, une traduction déjà passée par le rattrapage unitaire, et c'est sur quoi compte la
  reprise. Les écrire tôt laisserait, après un `--stop`, des planches en cache sans leur
  rattrapage — un demi-état qu'aucune commande ne rattraperait.
- **Le retour est différé** : rien ne s'affiche avant la fin du lot. Pour itérer sur un prompt,
  garder `planches: 1`.
- **En mode vision**, le lot est plafonné par `manga.lot.planches_vision` (4 par défaut) : une
  image pleine page par planche saturerait le contexte avant la première réplique.

### Modifié

- `prompts/manga_traducteur.md` — section « Plusieurs planches à la fois » (séparateurs,
  numérotation continue, ne pas reproduire les séparateurs). Le reste du prompt est inchangé :
  une planche seule produit exactement la même sortie qu'en 1.0.0.
- `quality_manga.bubbles_cap` devient un cas particulier de `bubbles_cap_lot(…, plafond=2048)`.
  Sa signature et son résultat ne bougent pas.

---

## [1.0.0] - 2026-08-16

**La brique manga sort de bêta, et le contexte cesse de s'arrêter au bord de la planche.**
MAJEUR *par exception* (cf. la règle de numérotation ci-dessus) : **rien n'est cassé**, aucun
cache n'est invalidé, aucune clé n'est retirée. Tous les nouveaux réglages ont un défaut
iso-comportement, sauf ceux dont l'effet est mesuré ci-dessous.

### Ce que « stable » recouvre, et ce qu'il ne recouvre pas

Sur les 258 planches à bulles des deux tomes du *manga A* : **257 en
numérotation complète**, **0 repli positionnel**, **0 kanji résiduel** sur 1 593 bulles.
C'est cela que « stable » qualifie.

⚠ **La réserve est nommée plutôt que masquée** : la LECTURE du texte hors bulle reste peu
fiable — `manga-ocr` est un modèle de dialogue et hallucine sur une onomatopée stylisée. D'où
`manga.onomatopees.mode: "rapport"` par défaut : on détecte, on lit, on traduit, on **rapporte**,
et on ne dessine rien sur la planche.

### Ajouté

- **Le mobilier de page n'est plus lu ni traduit.** Une zone hors bulle qui revient à la
  **même position** sur ≥ 30 % des planches est un filigrane de scan, pas du contenu — même
  raisonnement que la brique LN sur les bandeaux de PDF (`pipeline/extract.py`,
  `footer_frac_pages`). Mesuré sur le Vol.1 du *manga A* : **92 zones écartées en 2 groupes**
  (les filigranes des coins, présents sur 47 et 45 planches). L'étage `sfx` se scinde en
  détection → filtre → lecture, si bien que l'OCR **et** l'appel LLM sont épargnés.
- **Triage du texte hors bulle**, et c'est lui qui allège le plus. Une zone sans **aucun**
  caractère japonais n'a rien à traduire :

  | | manga A Vol.1 | manga B Chap.5 |
  |---|---:|---:|
  | mobilier (écarté) | 92 | 0 |
  | bruit latin, lecture hallucinée (écarté) | 15 | 12 |
  | ponctuation seule → rendue **sans LLM** | 81 | 47 |
  | vrai japonais → LLM | 260 | 158 |

  Soit **42 %** des zones du Vol.1 et **27 %** de celles de manga B retirées de la charge LLM
  sans rien perdre de traduisible. La ponctuation n'est pas du bruit : `！！` posé à côté d'un
  visage stupéfait est du contenu, et `typeset.latiniser` le rend en `!!` — fidèlement, là où
  un modèle broderait.
- **Contexte inter-planches élargi et rendu fiable.** La fenêtre passe de 6 répliques d'UNE
  planche à `manga.contexte.planches_precedentes: 3` (plafond `repliques_max: 18`). Coût
  mesuré : ~+100 tokens par prompt, **+4 %** du prefill d'un tome.
- **Fiche de contexte de l'ŒUVRE** (`manga.contexte`, agent `contexte_oeuvre`,
  `prompts/manga_contexte.md`) : registre, qui vouvoie qui, récurrences — ce que le glossaire,
  dictionnaire de termes, ne dit pas. **Un seul appel par tome**, mis en cache dans
  `.checkpoints/contexte.txt`, sur le patron éprouvé de `_passe_terminologie`. Entrée et sortie
  bornées, parce que chaque token de la fiche est payé une fois par planche.
- **Les corrections écrites à la main ne sont plus jamais écrasées.**
  `page_XXXX/traduction_manuelle.json` (`{index: texte}`) est lu et superposé après la
  traduction, jamais produit par le pipeline. Une réplique corrigée survit donc à
  `--from traduction` comme à `--from rendu` — elle était perdue en silence jusqu'ici.
  C'est la transposition de l'`Origin::User` de *koharu*, et la première fondation de la 2.0.0.
- **`projet.json`** — index de tome versionné (`manga/projet.py`) : format, version de l'outil,
  révision, empreinte par planche. La révision n'augmente **que** si le contenu bouge. C'est ce
  qu'une interface graphique lira pour ouvrir un tome sans rejouer le pipeline.

### Corrigé

- **Le détecteur de boucle accusait une traduction fidèle.** `_repetition` comparait les
  répliques rendues sans jamais regarder `c.sources`, pourtant présent dans le `Contexte`. Sur
  *manga B* pages 58 et 59, une foule scande un nom : l'OCR rend `マリアネラ` **six fois**,
  la traduction rend six fois « Marianna Lassar », et les deux planches étaient diagnostiquées
  « le modèle a bouclé » — deux des cinq boucles du tome, avec leurs retries dépensés pour rien.
  Une répétition n'est fautive que si elle **dépasse** celle de la source.
- **Le motif d'échec résiduel n'apparaissait dans aucune section du rapport.** Il était persisté
  dans le `qa.json` et nulle part ailleurs : les pages 58 et 59 de manga B étaient en échec sans
  qu'une ligne ne le dise. Nouvelle section.
- **Le contexte inter-planches transmettait des répliques périmées.** La variable de boucle
  n'était pas réinitialisée sur une planche sautée (`continue` du balayage B) : sur un run
  partiel, la planche 40 recevait celles de la 12. Et elle partait **vide** sur `--page N`,
  alors que `page_{N-1}/traduction.json` était sur le disque. Le contexte est désormais **lu
  depuis les checkpoints**, sans état de boucle : les trois cas (run complet, run partiel,
  planche isolée) donnent le même résultat. Le forçage du glossaire y est rejoué, sans quoi le
  contexte aurait transmis les orthographes que le glossaire interdit.

### Mesuré, puis écarté

- **Traduire tout un tome en un seul appel.** Entrée 22 070 + sortie 8 878 = **30 948 tokens**
  pour un `num_ctx` mesuré à **32 768** — 94,4 %, soit **1 820 tokens** laissés au raisonnement,
  quand celui-ci occupe **74 à 97 %** de la génération sur ce dépôt. Avec `thinking_budget`,
  dépassement de +14 180, et `qwen35` n'a pas de KV cache shifting : l'échec serait franc.
  Trois plafonds mordent avant (`bubbles_cap` retombe à 2 048 pour 8 878 nécessaires,
  `CEIL_DEFAUT` vaut 6 000), un seul numéro manquant sur 815 relancerait les 815, et l'unité
  d'arrêt propre passerait de 1 planche à 131. Le contexte s'élargit ; l'unité de travail reste
  la planche.
- **La traduction par lots de 20 planches** (7 appels au lieu de 131, 22 713 tokens au pire)
  reste ouverte et documentée, mais n'est pas livrée ici : elle demande un `bubbles_cap`
  proportionné, la re-répartition des répliques vers les bonnes planches, et fait passer l'unité
  d'arrêt propre de 1 à 20 planches. À valider sur un tome avant d'y toucher.

## [0.40.0] - 2026-08-16

**Le japonais posé sur le dessin est enfin lu, traduit et glosé.** MINEUR : nouvel étage de
cache `sfx`, nouvel agent, nouveau modèle CV, nouvelles clés de configuration. Aucun cache
existant n'est invalidé — les deux tomes déjà traduits reprennent sans un seul appel LLM de
traduction de planche.

### Le constat, et ce qu'il n'était pas

Après le run du Vol.2 du *manga A*, du japonais restait visible sur les
planches. Le diagnostic « régression de la traduction » est **faux**, et la mesure le dit :

| | Vol.1 | Vol.2 |
|---|---|---|
| traductions scannées (kanji / kana / ext. A) | 815 | 778 |
| **contenant du CJK** | **0** | **0** |
| traductions vides | 2 | **0** |
| planches en repli positionnel ou partiel | 0 | **0** |
| bulles détectées restées en japonais | 2 | **0** |

Les 127 planches à bulles du Vol.2 sont **toutes** en stratégie `numerotee`. Sur chaque
métrique comparable, le Vol.2 est égal ou meilleur que le Vol.1.

Le japonais visible était du **texte hors bulle** — onomatopées et narration posées sur le
dessin — que le détecteur ne cherchait pas : sur les 1 593 régions des deux tomes, `kind`
vaut `"bulle"` 1 593 fois. 23 planches du Vol.2 n'ont aucune détection, dont 13 de vrai
contenu (les pages 63-65 et 134-136 pèsent 450 à 720 Ko). Le Vol.1 a le même défaut. Ce
n'était pas une régression, c'était un angle mort — et **rien ne le comptait**.

### Ajouté

- **`manga/text_detection.py`** — détection du texte sur dessin par `comic-text-detector`
  (export ONNX, même `onnxruntime`, aucune dépendance nouvelle). Seule la sortie `seg`
  (masque de texte dense) est utilisée : mesuré page 63, la tête `blk` ne propose que
  3 boîtes au-dessus de 0,5, toutes sur du petit texte horizontal, quand la colonne de
  katakana géants qui barre la planche est parfaitement dessinée dans `seg`. Une tête
  entraînée sur des *blocs de texte* ne reconnaît pas un ゴォォォ de 400 px.
  ⚠ Code amont GPL-3.0, poids entraînés pour partie sur Manga109-s : à vérifier avant toute
  diffusion des planches.
- **Appariement texte↔bulle par containment de MASQUES** (idée reprise de *koharu*), et non
  par IoU de boîtes : une réplique de 200 px² dans un ballon de 40 000 px² donne un IoU de
  0,005 — « hors bulle » — et un containment de 1,0.
- **Groupement RELATIF des fragments.** Une onomatopée est faite de traits disjoints, et son
  espacement est proportionnel à son corps : aucun rayon de dilatation en pixels ne peut à la
  fois réunir des katakana de 90 px et ne pas souder deux répliques voisines. Mesuré page 63 :
  la colonne ゴォォォ sortait en **8 zones** — donc 8 lectures, 8 lignes de traduction et
  8 gloses contradictoires le long d'un seul son. Elle en fait **1**.
- **`manga/gloss.py` — la glose.** Le texte japonais n'est **jamais effacé** : l'effacer
  demanderait de reconstruire le dessin, donc un modèle génératif (LaMa chez *koharu*), ce que
  le principe directeur interdit. La traduction est posée **à côté**, dans la zone la plus
  calme parmi huit ancrages, avec un invariant testé : une glose ne recouvre jamais l'encre
  d'une onomatopée, ni le masque d'une bulle, ni une autre glose. Faute de place, **on ne pose
  rien et on le dit**.

  ⚠ **Le mode par défaut est `"rapport"`, pas `"glose"` : rien n'est dessiné sur la planche.**
  La détection est fiable ; la LECTURE ne l'est pas. `manga-ocr` est un modèle de **dialogue**,
  qui rend toujours une phrase japonaise plausible — sur une onomatopée stylisée, il invente.
  Mesuré sur le Vol.2, et les trois stratégies de découpe échouent également :

  | planche | vrai contenu | lecture obtenue |
  |---|---|---|
  | 63 | `ゴォォォ` (colonne de 1 470 px) | `うんなんじゃないか` |
  | 135 | onomatopées | `．．．` · `じゃ` · `じゃあ．．．` |
  | 25 | zone de dessin | `民主の人とセックスを` |

  Dessiner cela sur la planche violerait la règle qui gouverne toute la brique : *une mauvaise
  réplique dessinée est pire qu'une absence signalée*. En mode `"rapport"`, lectures et
  traductions sont listées dans `RAPPORT.md` sous un titre qui dit **« À RELIRE »** — donc
  utilisables pour lettrer à la main, sans toucher au dessin. `mode: "glose"` reste disponible
  en connaissance de cause : le PLACEMENT, lui, est sûr et testé ; c'est le CONTENU qui ne
  l'est pas.

  Sur du **texte libre** (narration, pensée hors bulle), en revanche, la chaîne fonctionne :
  page 25, `ああ．．．陽弥．．．` → **« Ah... Haruya... »**, et les deux filigranes de scan sont
  correctement rendus par une ligne vide, comme le prompt le demande.

- **L'OCR du texte hors bulle croppe au RECTANGLE, pas au masque d'encre** — à rebours de ce
  que fait `masked_crop` dans une bulle, et c'est une mesure qui l'impose. Le masque de
  segmentation coupe au pixel près et retire justement les demi-teintes dont le ViT se sert :
  `人間の場所．．．` (inventé) contre `ああ．．．陽弥．．．` (correct), `民主の人とセックスを`
  contre `ＲａwＬａｚｙ．ｓ．`. C'est le seul point où *koharu* avait raison contre notre
  réflexe. À l'intérieur d'une bulle, le masquage reste indispensable.
- `prompts/manga_onomatopees.md` + agent `manga_onomatopees` — un appel LLM **séparé** de
  celui de la planche. Le contrat de numérotation des bulles tient à 127/127 sur le Vol.2 : y
  greffer une seconde liste risquerait ce qui marche pour ce qui n'existe pas encore.
- Étage de cache **`sfx`** (`--from sfx`), dans des fichiers **séparés** (`sfx.json`,
  `sfx_traduction.json`). `ocr.json` et `traduction.json` s'alignent sur `regions.json` par
  position : y insérer les zones hors bulle aurait imposé un `FORMAT_VERSION = 4` avec
  migration, donc le risque de retraduire 300 planches.
- `RAPPORT.md` — trois sections neuves, dont **« Pages sans bulle MAIS porteuses de texte »**.
  C'est celle qui manquait : une pleine page d'action couverte de katakana était rangée avec
  les pages de garde.

### Corrigé

- **Une bulle vidée par la suppression de glyphes ne recevait pas le marqueur `…`.** Le test
  de vacuité (`typeset.py`) précédait `texte_dessinable` : une bulle « traduite » en japonais
  n'est pas vide au premier test, se vide au second (aucune police de la chaîne n'a de kana),
  et sortait donc **blanche et muette**. Avant la 0.24.0 le même cas sortait en carrés tofu —
  laid, mais visible et signalé. Le rendre silencieux était une régression d'observabilité.
- **`japonais_residuel` était masqué par `bulles_manquantes`.** `diagnostiquer` s'arrête au
  premier motif du registre ordonné : une sortie à la fois incomplète et japonaise était
  rapportée « numérotation incomplète », et le mot « japonais » n'apparaissait nulle part.
  Ajout de `diagnostiquer_tous` et `motifs_repliques` — le retry continue de se décider sur le
  motif principal.
- **`（）` et `！？` n'étaient pas du japonais.** `_japonais_residuel` utilisait `tokens.CJK`,
  la classe LARGE (celle du budget de tokens, qui englobe la ponctuation pleine chasse). Elle
  utilise désormais `tokens.CJK_TEXTE`, l'étroite — introduite au socle en 0.33.0 précisément
  parce que la brique manga avait dû s'en fabriquer une.
- **`_prefere` pouvait retenir la sortie la plus japonaise.** Le critère était purement
  quantitatif (nombre de lignes numérotées) : à nombre égal, on départage désormais contre
  `japonais_residuel`. Comme le japonais n'est pas dessinable, on préférait sans le savoir la
  version qui produit des bulles vides.
- **Un cache fautif n'était jamais recontrôlé.** La branche de reprise recopiait le motif du
  `qa.json` précédent : un `--from rendu` ne pouvait pas découvrir un défaut que le run initial
  n'avait pas vu. Un contrôle lexical, sans appel LLM, est rejoué sur les textes relus.
- **La toute première activation de la passe sautait le rendu.** Les zones étaient détectées
  et traduites, puis `stages_to_redo` retombait à `{"rendu"}` et l'écran de garde « page déjà
  générée » sautait la planche : les gloses n'étaient jamais dessinées. Le rendu est désormais
  refait quand le `sfx.json` d'une planche est plus récent que ce que son `qa.json` décrit.
- **Une lecture modifiée n'invalidait pas sa traduction.** Le cache ne comparait que le
  NOMBRE de zones : après correction de la stratégie de crop, l'OCR passait de `人間の場所…`
  à `ああ…陽弥…` et la traduction restait « L'endroit des humains… ». `save_sfx` compare
  désormais les textes et supprime `sfx_traduction.json` quand ils changent — sans repayer
  d'appel LLM sur une relecture identique.
- **45 bulles parfaitement normales étaient accusées.** Un remplissage bas ne fait pas une
  région bi-lobée : les 45 régions que le Vol.2 rangeait sous « bi-lobées SUSPECTES » ont été
  inspectées une par une — ballons de cri au contour en étoile, bulles à longue queue, une
  case de décor. **Pas un seul vrai double.** Le discriminant n'est pas le remplissage mais
  l'existence d'un **goulot** : `scinder_par_erosion` distingue désormais « aucun goulot »
  (bulle dentelée, aucune action requise) de « goulot trouvé, découpage refusé » (seul cas
  ambigu). Résultat mesuré sur le tome : **38 dentelées, 7 suspectes** au lieu de 45.

### Non fait, et pourquoi

- **Inpainting des onomatopées** (LaMa, comme *koharu*) — romprait « l'IA ne dessine jamais ».
- **RF-DETR 4 classes de *koharu*** — publié en `safetensors` seulement (imposerait `torch`),
  poids sous conditions Manga109 d'usage académique.
- **Découpe de lignes en DP et largeur par ligne de base** — **déjà livrées**, et plus strictes
  que chez *koharu* : `typeset.wrap_balanced` est une programmation dynamique à coût
  quadratique **avec contrainte de largeur dure** (*koharu* se contente d'une pénalité
  ×10 000), et `avails[k]` est calculé par bande de ligne sur le profil du masque réel.
- **Ordre de lecture ancré sur les cases** — mesuré, puis abandonné. `_coupe_xy` est déjà
  panel-aware *sans* détecter les cases (les gouttières entre cases sont celles entre groupes
  de bulles). Et les gouttières internes d'une planche ne sont pas mesurables par profil de
  projection sur ce matériel : sur 95 coupes du Vol.2, **2** tombent dans une bande claire
  détectée, les autres bandes trouvées étant les **marges de page**. Construire l'ordre de
  lecture là-dessus le dégraderait, au prix d'une montée de `FORMAT_VERSION` sur 300 planches.
  Le faire proprement demanderait une vraie détection de cases.

## [0.39.0] - 2026-08-16

**Un run de nuit ne meurt plus sur un timeout, et les furigana retrouvent les mots
composés.** MINEUR : deux nouvelles clés de configuration, un nouveau motif d'échec.
**Le glossaire de roman A est à refaire** — cf. « Migration ».

### Corrigé

- **Le collecteur de furigana perdait les mots composés — régression de la 0.34.0.**
  L'EPUB porte **2 668 balises `<ruby>` glosées caractère par caractère** (contre 5 472 en
  ruby de groupe). Sur celles-là, le collecteur appariait chaque idéogramme à SA syllabe —
  `堕`→`だ`, `竜`→`りゆう`, `講`→`こう` — et **perdait `堕竜講`→`だりゆうこう`**. J'avais écrit
  ce comportement pour traiter un ruby portant *plusieurs mots* (`千万丈塔` + `踏破儀式`),
  sans voir qu'il détruisait le cas le plus fréquent.

  Règle de distinction : toutes les bases d'un `<ruby>` font UN caractère → ruby par
  caractère → on n'enregistre que le composé. Sinon → chaque paire séparément.

  Le terminologue ne recevait donc, pour un nom propre, que des gloses d'un kanji isolé —
  inutilisables — ou la seule lecture de groupe existante, qui est parfois un **indicatif
  radio**. D'où un glossaire faux à la racine :

  | Glossaire 0.38.0 | Lecture réelle | Correct |
  |---|---|---|
  | `Enaga` (祭花) | まつりか **388×** vs エナガ一三七 1× | **Matsurika** — l'héroïne, nommée d'après son matricule |
  | `Doriryū-kō` (堕竜講) | だりゆうこう **81×** | **Daryūkō** — « Doriryū » était inventé |
  | `Suzugamo` (凜雪) | りんぜつ **15×** | **Rinsetsu** |
  | `Épée du Vrai Dieu` (真神) | まがみ **18×** = le loup-dieu | **Épée du Grand Loup** |
  | `Tetsukiba` (鉄機馬) | くろこま | **Kurokoma** |
  | `Kidou Sousou` (駆動装甲) | コンデイ | **Kondei** |

  Vérifié sur l'EPUB réel : 11 romanisations contestées sur 11 sont désormais correctes.

- **Le timeout était structurellement intenable.** `llm.timeout` valait 900 s à plat, alors
  que le budget du traducteur (`out_cap` 4 644 + `thinking_budget` 16 000 = **20 644
  tokens**) demande **1 376 s à 15 tok/s** et **4 129 s à 5 tok/s** — les deux débits
  mesurés. **Le pire cas autorisé ne tenait sous 900 s à aucun débit** : il aurait fallu
  soutenir 23 tok/s, jamais atteint. Un bloc nominal passait avec 12 % de marge.

  Le plafond est désormais **dérivé** : `max(llm.timeout, max_tokens / debit_plancher_tok_s)`,
  calculé par requête. `llm.timeout` devient un **plancher** (pour les petits appels :
  titres, terminologie) et non plus un plafond. Il se recalcule seul si `thinking_budget`,
  `max_block_tokens` ou le modèle changent — la contradiction ne peut plus revenir.

- **Le SDK OpenAI retentait dans notre dos, et multipliait l'attente par 3.** `max_retries`
  n'était jamais passé au constructeur : le SDK vaut **2** par défaut et **retente sur
  timeout**. Cumulé aux tentatives de l'enveloppe : **9 requêtes de 900 s, soit 2 h 15 par
  bloc**, sans un seul message — le SDK ne journalise rien. C'est ce silence qui a fait
  passer un terminal pourtant vivant pour figé. Le SDK est câblé à `max_retries=0` ; les
  tentatives sont gérées par l'enveloppe, qui les compte et les trace.

- **Un timeout persistant tuait le tome entier.** C'était le **seul motif d'échec LLM à
  être fatal**, par simple absence de branche : une `APITimeoutError` n'est ni une
  `RuntimeError`, ni un message contenant « vide » ou « réponse finale », donc elle ratait
  les deux portes de sortie non fatales et tombait sur le `raise`. Aucun `try/except` sur
  les huit niveaux d'appel jusqu'à `process_volume`, dont le `except BaseException` ferme
  les sockets et re-lève **sans écrire de rapport** — d'où un `RAPPORT.md` resté à
  l'horodatage du run précédent.

  Le timeout devient un motif de bloc, membre de `redecoupage_sur_echec`. Couper en deux y
  est un remède **causal** et non palliatif : deux moitiés génèrent deux fois moins.

  ⚠ Il est diagnostiqué **avant** `vide`. Les deux donnent une sortie vide, mais `vide`
  appartient à `_TRAD_GARBAGE` : les intervertir ferait ressortir **en japonais** un bloc
  que le modèle n'a simplement pas eu le temps de traiter.

- **Le commentaire sur la sémantique httpx était faux.** `read` n'est pas un plafond de
  durée totale mais un délai d'**inactivité** ; httpx n'offre aucun plafond total. Il ne se
  comporte en plafond que parce que les appels ne sont **pas** en streaming — un futur
  `stream=True` le retirerait silencieusement. Documenté sur place.

### Ajouté

- `llm.debit_plancher_tok_s` (5) — le débit le plus bas qu'on accepte sans conclure à une
  panne, base du timeout dérivé.
- `garde_fous.abandon_apres_timeouts_consecutifs` (3) — un timeout isolé se redécoupe, mais
  N d'affilée signifient que le serveur ne répond plus : continuer remplirait le tome de
  langue source, chaque bloc payé au prix d'un timeout complet. Au-delà du seuil, arrêt
  **propre** (rapport partiel écrit, checkpoints intacts). `0` = ne jamais abandonner.
- **L'attente devient lisible.** En `--verbose`, chaque bloc annonce AVANT l'appel son
  budget et son échéance (`bloc 7/24 en cours · budget 20 644 tok · expire dans 69min`).
  Une génération peut légitimement durer plus d'une heure ; une heure sans un octet est
  indiscernable d'un blocage.

### Migration

Le glossaire de `roman A` porte les romanisations fausses décrites ci-dessus :
l'archiver, le vider, puis relancer avec `--force`. Les deux chapitres déjà rendus et les
checkpoints de ch03 en dépendent.

## [0.38.0] - 2026-08-15

**`--from traduction` purge enfin le titre du chapitre.** CORRECTIF de reprise : aucun
changement sur un run complet. Aucune action requise.

### Corrigé

- **Un titre traduit survivait à toutes les relances.** `chNN/title.txt` vit à CÔTÉ des
  dossiers d'étape et non dedans : `_ck`, qui purge `chNN/<étape>/` quand `--from` cible
  cette étape, ne pouvait donc jamais l'atteindre. Le titre du run précédent était réutilisé
  indéfiniment — sur un pivot japonais, cela voulait dire un titre resté en japonais
  traversant chaque reprise, sans qu'aucune commande ne permette de s'en débarrasser à part
  `--force` ou une suppression à la main.

  Il est produit par le traducteur : il appartient à cette étape, et `--from traduction` le
  purge désormais. Une reprise qui ne retraduit pas (`--from mise_en_page`) le conserve —
  c'est un appel LLM de moins par chapitre.

## [0.37.0] - 2026-08-15

**Les motifs de chapitres de `config.yaml` complètent les défauts au lieu de les remplacer.**
MINEUR : `decoupage.chapter_patterns` change de sémantique. **Vérifié sans effet sur les
13 tomes du dépôt** — aucune action requise.

### Corrigé

- **Renseigner `chapter_patterns` désactivait les défauts multilingues.** Les deux appelants
  faisaient `config[...]["chapter_patterns"] or None`, et `detect_chapters` REMPLAÇAIT ses
  défauts par la liste reçue. Or `config.yaml` en fournit une, 100 % latine : le motif CJK
  `第N章` de `DEFAULT_CHAPTER_PATTERNS` n'était donc jamais actif. Un utilisateur qui ajoute
  « POV » ne demande pas à cesser de détecter « Prologue ».

  L'union se fait désormais **dans `detect_chapters`** et non chez les appelants :
  `sources.scan_volume` et `orchestrator.process_volume` lisent tous deux la clé, et la
  laisser à leur charge les ferait diverger au premier oubli.

### Risque évalué, puis écarté

Ajouter des motifs ne peut que **créer** des frontières de chapitre — donc décaler les
indices `chNN`, et avec eux tous les checkpoints et tous les `chapters/chNN.md`. C'était le
changement le plus risqué de la série.

Mesuré avant livraison sur **les 13 tomes** de `sources/` (11 projets, pivots en, fr et jp) :
le découpage est **identique**, titre pour titre, dans tous les cas. Les motifs de
`config.yaml` (`POV`, `NPC No.`, `Fragment`…) ne recoupent aucun des défauts, et les défauts
ne matchent rien que les listes utilisateur ne matchaient déjà.

Ce correctif n'a donc aucun effet aujourd'hui : c'est une robustesse pour les prochaines
œuvres à pivot CJK, dont les chapitres s'ouvrent sur `第一章` plutôt que sur `Chapter 1`.

## [0.36.0] - 2026-08-15

**Le rapport dit comment le run a été dimensionné, et ce qui a mal tourné.** MINEUR :
`RAPPORT.md` gagne quatre informations. Aucune action requise, aucune clé à ajouter, aucun
changement sur le texte produit.

Dernier lot d'observabilité de la série : les précédents ont corrigé des défauts qui étaient
tous restés invisibles pendant un run entier. Celui-ci s'attaque à cette invisibilité.

### Ajouté

- **Ligne « Découpage » en tête de rapport** : taille réelle des blocs, densité mesurée du
  pivot, budget en tokens, plafond de sortie et budget de raisonnement. Ce sont les trois
  chiffres sans lesquels « ~22000 tok générés » dans `perf.log` reste une énigme — il aura
  fallu les recalculer à la main pour comprendre le run du Vol.1. Exemple sur un pivot
  japonais :

      Découpage : 2285 car./bloc (densité 0.96 tok/car., budget 2200 tok)
                  · plafond de sortie ≤ 6000 tok + 16000 de raisonnement

- **Alerte quand le plafond de sortie sature.** `out_cap` a un maximum dur (6000 tokens,
  désormais nommé `quality.CEIL_DEFAUT`), et l'atteindre n'est possible qu'avec une langue
  dense : il faudrait 12 000 caractères latins dans un bloc, ce que `max_block_chars`
  interdit. Le voir saturer dit que `max_block_tokens` est mal dimensionné pour ce pivot, et
  que le plafond ne joue plus son rôle de filet. **C'est le témoin qui aurait rendu le défaut
  visible dès le premier chapitre du Vol.1**, où les 8 blocs sur 8 le saturaient.

- **Ligne « Japonais/chinois résiduel »**, y compris quand elle vaut zéro. Le motif était
  compté depuis la 0.35.0 mais n'apparaissait nulle part : un compteur qu'on ne lit jamais
  ne vaut pas mieux que pas de compteur.

- **Avertissement quand le pivot est seul.** `others` vide signifie que le traducteur n'a
  aucune source à recouper — ce n'est pas un défaut, c'est le cas de toute œuvre
  mono-source, mais c'est un fait de run qui explique une partie de la qualité obtenue et
  qui ne se lisait nulle part.

### Rappel des traces déjà livrées

La ligne « Budget de génération » (blocs coupés au plafond, budgets de raisonnement épuisés),
présente **aussi dans le rapport partiel** lu après un Ctrl+C, est arrivée en 0.32.0 ; la
section « Entrées de glossaire sans rendu français » en 0.35.0. Avec ce lot, chacun des
défauts diagnostiqués sur le run du Vol.1 laisserait désormais une trace lisible.

## [0.35.0] - 2026-08-15

**Le glossaire cesse d'ordonner au traducteur de recopier du japonais.** MINEUR : nouvelle
clé `garde_fous.cjk_residuel_seuil`, nouveau motif d'échec, `prompts/glossariste.md`
complété. Rendu des œuvres à pivot latin **inchangé au caractère près**, vérifié sur le
glossaire réel du manga A.

### Corrigé

- **Une entrée dont le `nom` est encore la graphie source n'est plus montrée au
  traducteur.** C'est LA correction qui coupe la boucle : `prompts/traducteur.md` ordonne
  « utilise le nom de cette entrée comme rendu français », donc lui présenter `- 天茜 —
  Jeune sorcier` lui ordonnait littéralement d'écrire 天茜 dans le texte français. Le
  masquage est **asymétrique** — le terminologue et le glossariste continuent de les voir,
  puisqu'ils sont là pour les réparer ; les masquer les ferait recréer en boucle.

  Mesuré sur le glossaire réel de roman A : le traducteur recevait **494 caractères
  CJK**, il en reçoit **0**. Le terminologue, lui, les voit toujours, marquées
  `[À ROMANISER]`.

- **`_norm` réduisait toute chaîne idéographique à la chaîne vide.** `_norm("八重山吹")`
  valait `""`. Conséquence en cascade, jamais visible : `build_index` n'indexait aucune
  entrée japonaise, `_find_any` rendait toujours `None`, `_merge_entity` répondait toujours
  « add », et les variantes japonaises étaient silencieusement jetées — d'où les 3 doublons
  purs de `glossaire.bak.yaml`.

  ⚠ **Le piège qui allait avec** : dakuten et handakuten sont des `Mn`, exactement comme les
  accents latins, mais ce ne sont pas des accents — ils distinguent des caractères. Les
  retirer confondait ハ / バ / パ, donc `ピカ` avec `ヒカ` : deux entités auraient fusionné en
  silence. `_strip_accents` les préserve désormais et recompose en NFC.

- **`termes_source` devient une clé de recherche.** Sur un pivot non latin, c'est la graphie
  d'origine qui est l'identité STABLE de l'entité — la romanisation, elle, varie d'un relevé
  à l'autre (« Amane » / « Amané »). Sans cet ajout, sortir le CJK des `variantes` aurait
  RETIRÉ du dédoublonnage au lieu d'en ajouter. Les deux chemins de `_find_any` (indexé et
  linéaire) partagent maintenant la même liste de formes : les laisser diverger faisait
  dédoublonner ou non selon qu'un index avait été fourni.

- **Un `force: true` sur une entrée non romanisée ne réécrit plus rien.** Les formes
  remplacées incluent `termes_source` : sur `不尽山`, il aurait réécrit `霊峰・不尽山` →
  `不尽山`, verrouillant le japonais dans le rendu de façon déterministe et sans appel LLM
  pour le trahir. Deux lignes, une classe entière de dégât futur.

### Ajouté

- **Réparation déterministe à l'entrée du glossaire.** Une graphie source dans `nom` ou
  `variantes` part vers `termes_source` ; une entrée sans forme latine est conservée — le
  retirer perdrait la description et le genre — mais marquée. Branchée au SEUL endroit où
  une entrée est créée, donc valable pour les trois producteurs : terminologue, glossariste
  et `--import-glossary`.

- **Motif `cjk_residuel`** dans le registre light novel, qui n'avait aucun contrôle de ce
  genre — alors que la brique manga en a un, et que la docstring de `core/quality.py` le
  citait en exemple sans qu'il ait jamais été implémenté. Un chapitre entier en japonais
  ressortait « ok ».

  Il **ne déclenche pas de redécoupage** (couper un bloc en deux ne fait pas traduire un nom
  propre : les deux moitiés reviendraient en japonais et le coût doublerait) et **ne fait pas
  retomber sur la langue source** (remplacer un français à noms japonais par du japonais à
  100 % serait une aggravation). La sortie est conservée et marquée AMBIGU.

  Tolère les formes que le glossaire autorise (`traduire: false`) et celles qu'il n'a pas
  encore romanisées — les bannir ferait boucler le retry sur une sortie pourtant conforme au
  glossaire qu'on a soi-même fourni. Ignore la ponctuation CJK, les marqueurs d'image et les
  commentaires. `cjk_residuel_seuil: 0` le désactive.

- **Section « Entrées de glossaire sans rendu français » dans `RAPPORT.md`.** Ces entrées
  étant masquées au traducteur, elles seraient autrement invisibles.

- **`prompts/glossariste.md`** porte enfin la règle appliquée côté manga depuis longtemps :
  `variantes` = orthographes latines légitimes, une forme fautive va dans `interdits`, une
  graphie source dans `termes_source`.

### État après ce lot

Sur roman A, **52 entrées sur 52** sont sans rendu français : le glossaire vu par le
traducteur est donc vide, et les 52 graphies sont tolérées par `cjk_residuel` (on ne peut pas
reprocher au traducteur d'écrire ce qu'on ne lui a pas appris à traduire). C'est l'état
attendu **avant** une relance de la terminologie : celle-ci, avec les furigana de la 0.34.0,
produira des noms latins qui repeupleront le glossaire du traducteur.

## [0.34.0] - 2026-08-15

**Le terminologue reçoit les lectures, et sait qu'il doit produire du français.** MINEUR :
prompts `prompts/terminologue.md` et `prompts/traducteur.md` réécrits, nouveau canal de
lectures à l'extraction. Aucune action requise, aucune clé à ajouter.

C'est le lot qui coupe la racine des 447 séquences japonaises du rendu : jusqu'ici le
terminologue ne voyait QUE du japonais (`others` est vide sur une œuvre mono-source) et rien
ne lui disait que `nom` devait être français. Il recopiait donc la graphie source — que le
glossaire présentait ensuite au traducteur comme « le rendu à respecter ».

### Ajouté

- **Les furigana sont relevés dans un lexique séparé, sans toucher au texte.** L'EPUB de
  roman A porte la prononciation de tous les noms fautifs — 天茜=あかね (**Akane**),
  碧燈=あおひ (**Aohi**), 八重山吹=ヤエヤマブキ (**Yaeyamabuki**) — soit **2 029 graphies
  glosées**. C'était exactement l'information manquante, et `ruby: "ignorer"` la jetait.

  **Pas de nouveau mode `ruby:` pour autant** : les inliner gonfle la source de 30 % et noie
  le traducteur, alors que le seul agent qui en a besoin est le terminologue, et seulement
  pour quelques noms par bloc. Les lectures sont donc collectées **toujours**, dans un canal
  à part (`Extracted.lectures`, `LangSource.lectures`) — le texte transmis aux agents est
  inchangé au caractère près.

- **Section « LECTURES (furigana) » dans le message du terminologue**, limitée aux graphies
  qui apparaissent dans SON bloc et plafonnée à 40, les plus longues d'abord (un nom composé
  est plus informatif qu'un kanji isolé). Mesuré sur un bloc de ~1 900 tokens : 126 gloses
  concernées, 40 envoyées, ~370 tokens.

- **Consigne de romanisation**, injectée dans le MESSAGE et non dans le prompt système :
  `nom` en alphabet latin, Hepburn pour les noms propres, traduction française pour les
  concepts, graphie d'origine dans `termes_source`. Dans le message parce que
  `prompts/terminologue.md` est **partagé avec la brique manga** et relu à chaque bloc de
  chaque œuvre, dont la grande majorité a un pivot latin.

  Actif uniquement quand la langue pivot n'est pas latine — détecté par le code de langue
  **ou** par la mesure, la table `langues.dossiers` étant éditable. Sur un pivot latin, le
  message du terminologue est identique au caractère près (un test le verrouille).

### Corrigé

- **`prompts/terminologue.md` interdisait de remplir `termes_source` sans section
  « SOURCE(S) ÉTRANGÈRE(S) »** — or cette section est vide précisément quand le pivot EST la
  langue source. C'était le verrou logique du bug : le modèle n'avait aucun endroit où mettre
  la graphie japonaise, alors il la mettait dans `nom`. La règle vaut désormais aussi quand
  le bloc lui-même est en langue non latine.
- **`prompts/traducteur.md`** disait « ne laisse aucune forme source **anglaise** non
  traduite » — le japonais n'était pas couvert.
- **Un `<ruby>` à plusieurs couples était mal apparié dans le lexique.**
  `<ruby>千万丈塔<rt>…</rt>踏破儀式<rt>…</rt></ruby>` donnait la paire fausse
  « 千万丈塔踏破儀式 ». Chaque base est maintenant appariée à SON `<rt>` — le même piège que
  le rendu du texte évitait déjà.
- **Une graphie glosée de plusieurs façons retient la lecture la plus FRÉQUENTE**, pas la
  première rencontrée. 434 graphies sur 2 029 sont dans ce cas, presque toujours une lecture
  canonique plus des *gikun* isolés : 天茜 est glosé あかね **458 fois** et きようだい 1 fois.
  La règle « première rencontrée » choisissait parfois le cas isolé. À égalité stricte,
  l'ordre du spine départage — arbitraire, mais reproductible.

### Non vérifié à ce stade

L'effet sur le rendu demande un run LLM réel. Ce qui est vérifié ici : les lectures arrivent
bien au terminologue, la consigne n'apparaît que sur un pivot non latin, et le texte source
comme les œuvres à pivot latin sont inchangés.

## [0.33.0] - 2026-08-15

**Le socle qui sait quelle graphie va dans quel champ.** MINEUR : nouveau module
`core/glossary_lang.py`. **Aucun effet à l'exécution** — rien ne l'appelle encore ; c'est la
fondation des deux lots suivants, qui feront disparaître les 447 séquences japonaises du
rendu. Aucune action requise.

### Ajouté

- **`core/glossary_lang.py`** — détecter le CJK, et remettre chaque graphie dans le champ
  qui lui revient. Le schéma distingue depuis toujours le rendu français (`nom`) de la
  graphie source (`termes_source`), mais **rien dans le nom du champ `nom` ne dit qu'il doit
  être en français** : sur une œuvre dont la langue pivot EST la langue source, le
  terminologue écrit le headword japonais, le glossaire le présente au traducteur comme « le
  rendu à respecter », et le traducteur obéit.

  Trois raisons d'en faire un module du SOCLE plutôt qu'un correctif local : le glossaire
  est **partagé entre les deux briques** (`manga/terminology.py` écrit dans le même fichier,
  une validation cantonnée à `pipeline/` laisserait la moitié des producteurs la
  contourner) ; les jeux de caractères CJK ont **déjà divergé une fois** ; et la réparation
  doit être **pure**, pour se brancher sur les trois producteurs en un seul point.

  `reparer_entree` est pure, idempotente, et ne mute pas son entrée. Quatre cas :
  une **variante** en CJK part vers `termes_source` (y laisser une graphie source la fait
  concurrencer les orthographes latines dans la clé du dédoublonneur) ; un **`nom` en CJK
  avec une variante latine** est réparé silencieusement ; un **`nom` en CJK sans forme
  latine** est CONSERVÉ — le retirer perdrait la description et le genre — mais marqué
  `a_romaniser: true` et signalé ; et `nom == termes_source` **en latin** n'est pas un
  défaut (sur une source anglaise, `Semifer` inchangé est exactement ce qu'on veut).

  Le module **ne romanise rien** : transformer 天茜 en « Akane » demande la lecture あかね,
  que seul le texte source porte. C'est le rôle du terminologue, à qui les furigana seront
  fournis.

- `tokens.CLASSE_CJK_TEXTE` : le corps de la classe de caractères, exposé à côté du regex
  compilé. `glossary_build._norm` en aura besoin pour construire sa classe négative, et le
  dupliquer rouvrirait exactement la divergence que ce module existe pour fermer. Le regex
  lui-même est **inchangé**, il est simplement construit à partir de cette chaîne.

### Vérifié sur les données réelles

- `sources/roman A/glossaire.yaml` : **52 entrées sur 52** ressortent marquées
  `a_romaniser` — aucune n'a de forme latine, ce qui confirme le diagnostic ; 3 entrées ont
  une variante CJK qui part vers `termes_source`.
- `sources/manga A/glossaire.yaml` (source anglaise) : 6 entrées sur 28
  changent, toutes de la même façon — une graphie déjà présente dans `termes_source` quitte
  `variantes` (ex. `Mitsukage`, `variantes: [三影, Mikage]` → `[Mikage]`). **Aucune
  information perdue**, et sans effet pratique : `_norm("三影")` rend `""`, donc cette forme
  était déjà invisible au dédoublonneur.

## [0.32.0] - 2026-08-15

**Un bloc qui manque de budget est redécoupé, au lieu d'être rendu dégradé en silence.**
MINEUR : deux nouveaux motifs d'échec, et un paramètre optionnel sur `LLM.chat` /
`Agent.run`. Aucune action requise, aucune clé de configuration à ajouter.

Le redécoupage-relance existait depuis la 0.22.0 et son commentaire citait le budget de
réflexion épuisé comme **cas d'école**. Il n'a jamais été atteint : trois court-circuits le
lui interdisaient.

### Corrigé

- **Le repli sans raisonnement n'est plus le premier réflexe, mais le dernier recours.**
  Quand le raisonnement épuisait tout le budget, le client relançait **lui-même** l'appel en
  `reasoning_effort: "none"` et rendait le résultat dégradé comme une réponse normale.
  L'orchestrateur concluait au succès et ne redécoupait jamais — alors que **deux moitiés
  raisonnées valent mieux qu'un bloc entier non raisonné**. Ce filet avait été écrit *avant*
  que le redécoupage n'existe ; l'arbitrage n'avait jamais été revu.

  `LLM.chat` accepte désormais `repli_sans_raisonnement`. L'orchestrateur le **ferme** tant
  que le bloc reste redécoupable — avec exactement la même condition que le redécoupage,
  calculée avant l'appel — et ne le rouvre qu'à la profondeur maximale ou sous
  `redecoupage_taille_min`. Refusé, `chat()` rend `""` avec `last_reason` renseigné, ce qui
  emprunte le chemin de redécoupage déjà en place. Le défaut d'instance reste `True` : tous
  les autres appelants, dont toute la brique manga, gardent le filet.

- **`finish_reason == "length"` et le dépassement de réflexion déclenchent enfin quelque
  chose.** Les deux étaient détectés et comptés depuis la 0.22.0, mais `last_reason` n'était
  lu qu'**à l'intérieur** de la branche de redécoupage, pour enrichir un message : le
  contrat annoncé dans son propre commentaire n'était pas honoré. Ils deviennent deux motifs
  d'échec de plein droit, `troncature_length` et `thinking_overflow`, membres de
  `redecoupage_sur_echec`.

  Aucun garde-fou existant ne pouvait les rattraper : `emballement` compare la sortie au
  `cap` de l'appelant, alors que le plafond réellement envoyé vaut `cap + thinking_budget` —
  une sortie coupée après un long raisonnement peut donc être **courte**, très loin des 95 %
  du `cap`. C'est ce qui rendait ces échecs invisibles.

  Ni l'un ni l'autre n'entraîne de repli sur la langue source : un texte tronqué reste du
  français exploitable, il est conservé et marqué `<!-- AMBIGU: … -->`.

- **La cause est relevée après CHAQUE appel.** Le client remet `last_reason` à `None` à
  chaque `chat()`, et le moteur de retry peut appeler deux fois : la lecture unique après
  coup ne décrivait que le second appel.

- **Le repli vérifie `finish_reason` sur sa propre réponse.** Une réponse de secours
  elle-même coupée au plafond revenait comme un succès ordinaire.

### Ajouté

- **Une troncature laisse une trace.** Elle n'était que comptée : sur roman A Vol.1,
  deux blocs coupés en plein mot n'apparaissaient dans `perf.log` que comme des blocs
  ordinaires. Le message y part désormais avec le nombre de tokens générés.
- **Ligne « Budget de génération » dans `RAPPORT.md`** — nombre de blocs coupés net au
  plafond et de budgets de raisonnement épuisés, distincts des replis de qualité. Présente
  **aussi dans le rapport partiel**, celui qu'on lit après un Ctrl+C, et qui affichait
  « ok : 33 · perte de mots : 0 » sur un run contenant deux blocs amputés. Elle complète la
  ligne de `core/report.py`, qui compte les APPELS LLM là où celle-ci compte les BLOCS.

### Note d'implémentation

Il n'existe **pas** de chemin « repli accepté en silence » : `thinking_overflow` étant un
motif à part entière, une sortie obtenue sans raisonnement est toujours diagnostiquée et ne
peut jamais ressortir comme une traduction ordinaire. Quand plus rien n'est redécoupable,
elle suit le chemin d'échec ordinaire — conservée et marquée. Un test le verrouille.

## [0.31.0] - 2026-08-15

**Un bloc pèse le même travail quelle que soit la langue.** MINEUR : nouvelle clé
`decoupage.max_block_tokens`, `llm.think` accepte un niveau nommé, `thinking_budget`
s'affine par endpoint. **Découpe des œuvres à pivot latin inchangée**, vérifié bloc pour
bloc sur roman D (61 blocs), roman E (110) et roman C.

### Ajouté

- **`decoupage.max_block_tokens` (2200) : le budget d'un bloc s'exprime en tokens, plus en
  caractères.** Un bloc de 6 000 caractères ne pèse pas la même chose selon la langue :
  ~1 500 tokens en anglais (≈4 caractères/token), ~5 900 en japonais (≈1 token/caractère).
  Découper en caractères revient à donner au modèle quatre fois plus de travail par bloc sur
  un pivot CJK.

  La limite effective devient `min(max_block_chars, max_block_tokens / densité mesurée)`,
  la densité étant calculée sur le chapitre lui-même. `max_block_chars` garde donc
  exactement sa sémantique de **plafond dur**, et la limite dérivée ne peut que rétrécir :

  | pivot | densité mesurée | limite dérivée | effet |
  |---|---:|---:|---|
  | anglais / français | 0,250 | 8 800 car. | > plafond → **découpe inchangée** |
  | japonais | 0,972 | 2 258 car. | 43 → 128 blocs sur le tome |

  **Ce que ça corrige.** Le plafond de sortie `out_cap` saturait son maximum dur (6 000)
  sur **8 blocs sur 8** du chapitre 3 de roman A — une situation impossible avec un
  pivot latin, où il faudrait 12 000 caractères dans un bloc. Il retombe à 4 644 et
  redevient ce qu'il est censé être : un filet, pas un régime de croisière. C'est la cause
  des deux blocs coupés en plein mot corrigés en 0.29.1, traitée à la racine.

  **Ce que ça ne corrige pas.** Le temps de mur n'est pas garanti meilleur. Le raisonnement
  croît avec la taille de l'entrée : à découpage plus fin, le total sur un chapitre ne
  s'effondre pas mécaniquement (il ne baisse que si le raisonnement est sur-linéaire, ce qui
  est probable mais non mesuré ici). Le prefill, lui, **augmente** — le glossaire est
  ré-injecté à chaque bloc, soit ~768 000 tokens de prompt sur ce chapitre contre ~430 000.
  Le gain visé est la justesse, pas la vitesse.

- **`llm.think` accepte un niveau nommé** — `"low"`, `"medium"`, `"high"` — en plus de
  `true`/`false` (`true` reste `"medium"`). Le niveau pèse lourd : sur roman A Vol.1,
  `"medium"` sur des blocs japonais de ~5 600 tokens a fait partir **74 à 97 % de la
  génération** dans le `<think>` — 156 500 tokens de raisonnement pour 21 400 de traduction
  sur le seul chapitre 3. Réduire les blocs traite la cause ; `"low"` est le levier suivant.
  Un niveau inconnu échoue au premier appel avec un message actionnable plutôt que de partir
  chez Ollama et de revenir en 400 opaque.

- **`thinking_budget` s'affine par endpoint** (`reflexion: { think: true, thinking_budget: 8000 }`),
  comme `base_url` et `think` : le budget de raisonnement n'a de sens qu'au regard du niveau
  et de la taille des blocs, or les deux se règlent déjà là. La valeur globale reste
  **inchangée à 16 000** : l'endpoint `reflexion` sert aussi au glossariste, dont l'entrée
  n'est pas dimensionnée par bloc mais par le glossaire entier (`optimize_glossary_file`) —
  un budget calé sur des blocs de 2 200 tokens le tronquerait. La variante économe est
  documentée, commentée, dans `config.yaml`.

### Corrigé

- **L'estimation de fin de run tient compte du découpage réel.** Elle divisait la taille du
  chapitre par `max_block_chars`, ce qui la rendait ~4× trop optimiste sur un pivot dense —
  sur un run qui dure déjà des heures.

- `bool("none")` valant `True`, un agent explicitement réglé sans raisonnement se serait vu
  accorder le budget de tokens supplémentaire. Un test le verrouille.

### Note de migration

Changer `max_block_tokens` déplace les frontières de blocs : le garde-fou de la 0.30.0
détecte le nouveau découpage, invalide les checkpoints des étages concernés et le dit
(`[traduction] découpage modifié (9 → 24 blocs)`). Rien à supprimer à la main.

## [0.30.0] - 2026-08-15

**Changer le découpage ne recompose plus un chapitre avec des morceaux qui ne se suivent
pas.** MINEUR : nouveau garde-fou, et un fichier `_decoupage.sig` par étage sous
`.checkpoints/`. **Aucune action requise, aucun tome déjà traité n'est invalidé** — une
signature absente est adoptée telle quelle.

Préalable au lot suivant, qui rend la taille des blocs sensible à la densité de la langue
pivot : sans ce filet, la première relance après ce changement aurait corrompu les
chapitres en cours, sans un mot.

### Ajouté

- **Les checkpoints d'un étage portent l'empreinte du découpage qui les a produits.** Ils
  sont indexés par NUMÉRO de bloc (`000.txt`, `001.txt`…) et rechargés tels quels. Si le
  découpage change entre deux runs — nouvelle valeur de `max_block_chars`, source
  ré-extraite, algorithme de `split_blocks` modifié — les anciens fichiers étaient relus en
  face des NOUVEAUX blocs : le chapitre se retrouvait recomposé de morceaux qui ne se
  suivent pas. Silencieusement, et sans un seul appel LLM pour le trahir.

  L'empreinte porte le **nombre de blocs et leurs longueurs**, pas leur contenu : c'est la
  frontière qui casse l'alignement, et empreinter le texte ferait jeter des heures de cache
  pour une différence d'extraction sans conséquence sur les indices. Quand elle diffère,
  l'étage est vidé et recalculé, avec un avertissement nommant les deux découpages
  (`[traduction] découpage modifié (4 → 1 blocs) — cache de l'étape invalidé et recalculé`),
  qui part aussi dans `perf.log`.

  Les cinq étages indexés par bloc sont couverts, y compris les deux qui ne passent pas par
  `_run_blocks` : la boucle de terminologie de `process_volume` — la plus pernicieuse, car
  elle re-fusionne ses relevés dans le glossaire **sans appel LLM**, donc sans rien coûter
  ni signaler — et celle de `--extract-glossary`.

  Le seul chemin où le problème pouvait réellement se produire est la reprise d'un run
  **interrompu** après un changement de découpage : `--from` purge déjà l'étage visé et ses
  suivants, et un chapitre dont le `.md` existe est sauté entièrement. C'est ce scénario que
  verrouille `test_checkpoints_invalides_si_le_decoupage_change`.

- Le marqueur s'appelle `_decoupage.sig`, **sans `.txt` délibérément** :
  `stagediff._stage_blocks` liste les blocs d'un étage par `glob("*.txt")`, et un marqueur
  en `.txt` s'y serait ajouté comme un bloc fantôme en fin de liste (le chiffre trie avant
  l'underscore). Même raison que le `_done` de `--extract-glossary`. Un test le verrouille.

## [0.29.1] - 2026-08-15

**Un bloc japonais tronqué en plein mot ne passe plus pour un bloc réussi.** CORRECTIF :
sortie **inchangée au caractère près** sur toutes les œuvres à pivot latin (vérifié sur les
148 fichiers de `build/`). Aucune action requise.

Premier tome du dépôt dont la langue pivot est le japonais — toutes les autres œuvres ont un
pivot anglais ou français. Le run de `roman A` Vol.1 a rendu deux blocs coupés en
plein mot (`ch03` 4/9 et 7/9, « … l'invoqueur finissait in » et « … pour neutral »), que le
`RAPPORT.md` a comptés dans ses « ok : 33 · perte de mots : 0 ».

### Corrigé

- **Le garde-fou `perte_mots` n'est plus aveugle sur un pivot CJK.** `_word_count` s'appuie
  sur `\w`, qui **inclut les idéogrammes** en Unicode : le japonais s'écrivant sans espaces,
  une phrase entière comptait pour UN SEUL mot, et une clause entre `、` et `。` pour un
  autre. Sur le bloc 4 du ch03, la source pesait ainsi 18 « mots » au lieu de 116 — le seuil
  de 0,60 tombait à 11, et le fragment tronqué (15 mots français) passait au-dessus. Les
  suites CJK sont désormais neutralisées avant le comptage des mots latins, puis recomptées à
  raison d'un demi-mot par caractère.

  Mesuré sur les 9 blocs du chapitre : le ratio sortie/entrée vaut **1,19 à 1,33 sur les
  7 blocs sains** et **0,17 / 0,26 sur les 2 tronqués**. Le seuil `perte_mots_ratio.traducteur`
  déjà en configuration les sépare avec le double de marge de chaque côté — **il n'a pas
  bougé**. Et comme `perte_mots` fait partie de `redecoupage_sur_echec`, ces deux blocs
  seront désormais coupés en deux et relancés au lieu d'être conservés tronqués.

  Sur un texte sans caractère CJK, la substitution est l'identité et le terme ajouté vaut
  zéro : le résultat est **strictement** celui d'avant. `test_word_count_basic` le vérifie
  sans avoir été modifié, et `test_word_count_inchange_sans_cjk` l'exige explicitement.

### Ajouté

- `tokens.CJK_TEXTE` : classe de caractères **étroite** (kana, idéogrammes, hangûl) pour
  décider si un texte *porte* du japonais, à côté de `tokens.CJK` qui reste **large** pour
  le budget de tokens. Les confondre est un piège déjà payé par la brique manga, qui avait dû
  se fabriquer la sienne après avoir déclaré « du japonais » sur une bulle ne contenant que
  `（）` : ici, `CJK` faisait compter huit guillemets `「」『』` pour quatre mots — c'est le
  seul fichier latin du dépôt qu'elle faisait diverger. `tokens.CJK` devient public au
  passage (`_CJK` reste un alias, les call sites manga et un test s'en servent).

### Connu, non corrigé à ce stade

Trois défauts du même run restent ouverts, documentés et chiffrés : les blocs de traduction
génèrent 17 000 à 26 000 tokens dont **74 à 97 % de raisonnement** (la découpe est en
caractères, or le japonais fait ~1 token/caractère) ; le repli sans-raisonnement de
`core/llm.py` court-circuite le redécoupage qu'il devrait déclencher ; et le glossaire écrit
la graphie japonaise dans le champ `nom`, que le traducteur recopie ensuite fidèlement
(447 séquences CJK dans le rendu).

## [0.29.0] - 2026-08-15

**Un démarrage d'OCR silencieux et hors ligne, et un bilan terminologique qu'on voit.** MINEUR :
nouvelle clé `manga.ocr.hors_ligne` (défaut `"auto"`, iso-comportement au premier lancement).
Aucune action requise.

Trois questions sont nées du run du Vol.2. Une seule décrivait un vrai défaut du pipeline ; les
deux autres étaient des malentendus **que le code entretenait**, et c'est cela qui est corrigé.

### Corrigé

- **L'OCR ne contacte plus Hugging Face à chaque lancement.** Le modèle était en cache — la
  barre `Loading weights: 264/264 [00:00…]` est un chargement disque en moins d'une seconde —
  mais `from_pretrained` revalidait la révision auprès du Hub à chaque run, d'où la ligne
  « You are sending unauthenticated requests to the HF Hub » et l'impression d'un
  téléchargement. Il est désormais chargé par son **chemin local** dès qu'il est en cache :
  plus de latence réseau, un run possible hors ligne, et surtout **la révision est figée** —
  une nouvelle révision ne peut plus arriver en plein tome et changer l'OCR sans prévenir.
  Le cache en contenait déjà deux.
- **L'avertissement `ViTImageProcessor requires torchvision` est tu.** Il est émis à l'import
  de `ViTImageProcessor`, donc de `manga_ocr` — pas à celui de `transformers` :
  `set_verbosity_error()` posé **avant** cet import suffit, torchvision installé ou non. Les
  erreurs réelles remontent toujours, et les lignes de `manga_ocr` restent.

### Ajouté

- **Le bilan terminologique est redit à la FIN du run.** Sa seule trace console était écrite
  *avant la première planche* : sur 150 planches, elle avait défilé depuis longtemps. Deux
  fois la question « la terminologie ne s'est pas déclenchée » a été posée sur des runs où
  elle avait parfaitement tourné — `RAPPORT.md` le disait, la console non. Trois états
  nommés, comme dans le rapport : passe **désactivée** (avec la clé à décommenter), planches
  relevées (avec le total du glossaire et son chemin), ou **aucune planche à relever ce run**
  — ce dernier cas est celui de tout `--from rendu`, et « 0 planche relevée » s'y lisait
  comme un échec.
- `manga.ocr.hors_ligne` : `"auto"` (défaut, hors ligne dès que le modèle est en cache),
  `true` (exiger le cache, échouer clairement sinon — un mode strict qui téléchargerait en
  douce ne servirait à rien), `false` (comportement d'avant).
- `requirements-manga.txt` documente `torchvision` en **option**, avec la roue adaptée au
  build de `torch` : sans lui `transformers` se rabat sur un processeur d'image PIL, plus
  lent. Volontairement pas une dépendance dure — un `pip install torchvision` non qualifié
  réinstallerait un `torch` incompatible.

### Note d'exploitation (aucun changement de code)

`qwen3.8:27b` n'est pas plus gros que `qwen3.6:27b` — les deux font **17 Go, 27 B, Q4_K_M**.
Mais son Modelfile porte **deux `FROM`** et `PARAMETER draft_num_predict 4` : c'est du
**décodage spéculatif**, donc un second modèle « brouillon » chargé à côté du principal. D'où
la mémoire, et une vitesse mesurée à **~7 tok/s contre ~18,5** sur le tome précédent. Le levier
est un Modelfile dérivé avec `PARAMETER draft_num_predict 0` — un réglage Ollama, comme
`num_ctx`, pas un réglage du pipeline.

## [0.28.0] - 2026-08-15

**Plus de boîte « Polices manquantes » à l'ouverture d'un PSD.** MINEUR : nouvel outil
`tools/installer_polices.ps1`. Le nom de police écrit dans les PSD est corrigé — régénérer un
tome par `--from rendu` n'est utile que si son lettrage n'était pas en ComicNeue-**Bold**, dont
le nom était déjà juste.

Un calque de texte ne peut pas embarquer sa police : il n'en déclare que le **nom PostScript**,
et Photoshop cherche la police correspondante parmi celles **installées**. Le lettrage est
dessiné avec les fichiers de `templates/fonts/`, qui n'y sont pas — d'où la boîte. Interrogé en
COM, Photoshop connaît **800 polices et aucune `ComicNeue-*`**.

Ce n'est pas cosmétique : tant que la police manque, Photoshop **substitue dès la première
modification**, et la bulle réécrite jure avec ses voisines restées sur les pixels d'origine.

### Ajouté

- **`tools/installer_polices.ps1`** — installe les quatre polices livrées **pour l'utilisateur
  courant** : copie sous `%LOCALAPPDATA%\Microsoft\Windows\Fonts` et inscription dans `HKCU`,
  donc **aucun droit administrateur** et rien qui touche les autres comptes. `-Machine` pour
  l'installation classique, `-Desinstaller` pour retirer exactement ce qui a été posé,
  idempotent, avec diffusion de `WM_FONTCHANGE` pour les applications déjà lancées.
- **Le validateur PSD vérifie les polices.** `tools/valider_psd_photoshop.ps1` interroge
  `Application.Fonts` — la liste même que Photoshop consulte pour décider d'afficher la boîte —
  et nomme les absentes. Une police manquante devient une ligne de rapport, pas une modale.
  `RAPPORT.md` renvoie désormais vers l'installateur plutôt que vers un README.

### Corrigé

- **Le nom PostScript était deviné, et parfois faux.** `psd.nom_postscript` concaténait le
  `(famille, style)` de Pillow ; il **lit** maintenant l'entrée ID 6 de la table `name` du
  fichier, seule chaîne qui fasse autorité. L'heuristique reste en repli pour les polices dont
  la table est illisible.

  Mesuré : exacte pour Bold, Italic et BoldItalic — **fausse pour `ComicNeue-Regular`**, dont
  elle supprimait le suffixe, et **fausse pour Arial**, dont le vrai nom est `ArialMT`. Un PSD
  réclamait alors une police *inexistante* : l'installer n'y aurait rien changé, et le repli
  Arial de la chaîne était concerné aussi.
- **Le lecteur de la table `name` traitait mal la plateforme 0.** Les plateformes 3 (Windows)
  et 0 (Unicode) encodent en UTF-16BE, seule la 1 (Macintosh) est sur un octet. N'en traiter
  qu'une rendait ` A r i a l M T` — des NUL pris pour des caractères, invisibles à l'affichage.

### Vérifié de bout en bout

Aller-retour complet sur Photoshop 21.0.1 : polices absentes → le validateur les nomme et
échoue · installées → « les polices du document sont connues de Photoshop », sur le PSD minimal
comme sur une planche réelle à 10 calques · désinstallées → il les re-signale. La machine
revient exactement à son état d'avant.

## [0.27.0] - 2026-08-15

**Les calques de texte des PSD sont réécrivables — validé par Photoshop lui-même.** MINEUR :
le défaut de `manga.rendu.psd_texte` passe à `"type"`. Aucune action requise ; `--from rendu`
régénère les PSD d'un tome existant sans un seul appel LLM.

Trois tentatives avaient échoué faute d'une boucle de retour — alerte « Problèmes à la lecture
des calques » puis dégradation en pixels (v0.18/0.19.0), plantage à l'ouverture sans même un
message (v0.19.1), repli prudent sur `rasterise` (v0.21.0). `psd-tools` valide la conformité à
la **spécification** ; Photoshop valide ce qu'Adobe **accepte**, et c'est le second qui décide.

### Ajouté

- **`tools/valider_psd_photoshop.ps1`** — pilote Photoshop par son automation COM : ouvre le
  fichier, affirme le type de chaque calque **selon Photoshop** (`LayerKind.TEXTLAYER`), relit
  `TextItem.Contents`, la police et le corps, puis **tente une réécriture** avant de refermer
  sans enregistrer. C'est la seule preuve qui compte : un calque peut être déclaré de type,
  s'afficher correctement, et refuser malgré tout l'outil Texte — exactement ce que Photopea
  montrait en v0.19.1. Outil manuel (il ouvre l'application), donc jamais dans pytest.

### Modifié

- **`manga.rendu.psd_texte` vaut désormais `"type"`.** Validé sur Photoshop 21.0.1 : le PSD
  minimal de `--psd-test`, puis **quatre planches réelles du Vol.1 et 34 calques** — accents,
  apostrophes, guillemets français, paragraphes multi-lignes, et le point médian substitué de
  la page 147. Tous annoncés de type, tous relus, tous réécrits.

### Corrigé

- **Un test reposait sur le `config.yaml` livré au lieu de poser sa prémisse.**
  `test_sans_agent_terminologue_le_glossaire_nest_jamais_reecrit` supposait que le
  terminologue était commenté par défaut ; l'activer — ce que le rapport recommande
  précisément depuis la v0.23.0 — faisait mesurer au test le contraire de son nom.

### Mesuré

- **Le mode `type` ne coûte rien en fidélité.** Le calque porte à la fois nos pixels *et*
  l'information de texte : la planche composée par Photoshop est **identique au pixel près** à
  celle que le lettrage a dessinée — **0 pixel d'écart sur 1 800 000**, écart maximal 0. Le
  texte n'est re-rendu que le jour où on le modifie. Le choix n'est donc plus un arbitrage
  entre fidélité et éditabilité : `type` domine `rasterise` sur les deux plans.
- Les corps sont correctement convertis en points : Photoshop lit 6,5 pt là où le lettrage a
  dessiné 27 px, ce qui est exactement `27 × 72 / 300` pour un document à 300 dpi.

## [0.26.0] - 2026-08-15

**Relancer la détection d'une planche, après avoir vu ce que ça donnerait.** MINEUR : deux
drapeaux `--conf` / `--iou`, un outil `tools/apercu_detection.py`, un module
`manga/detection_retry.py`. Aucune action requise, aucun cache invalidé.

### Le fait qui rend tout cela peu coûteux

`conf_threshold` et `iou_threshold` ne servent **qu'au post-traitement** : le réseau ne les
voit jamais. `BubbleDetector` sépare donc `inferer()` de `regions_de()`, et balayer vingt et
un réglages sur une planche coûte **une inférence et vingt et un post-traitements**.

### Ajouté

- **`tools/apercu_detection.py`** — prévisualise une relance sans rien écrire. Une ligne par
  réglage : bulles trouvées, gagnées, perdues, score médian, **régions que le nettoyage
  refuserait**, px² repeints, verdict. `--vignette` trace gagnées/perdues/conservées en
  couleurs, parce que deux faux positifs sur du dessin se voient d'un coup d'œil et se lisent
  très mal dans une colonne de chiffres.
- **`manga/detection_retry.py`** — l'arbitre. Numpy pur, sans image ni E/S, donc testable sans
  GPU. **Véto** si une vraie bulle disparaît, si une bulle gagnée serait refusée par le
  nettoyage, si deux masques se recouvrent, ou si le nombre de bulles explose. **Gain** si une
  bulle est gagnée, si un faux positif est écarté, ou si la géométrie s'améliore.

  La règle centrale ne coûte rien de neuf : le nettoyage **refuse déjà** de toucher une région
  sous `seuil_abandon` (0,35, posé dans un creux mesuré de la distribution). *Une région que le
  nettoyeur refuserait de nettoyer ne doit pas être détectée* — et la règle joue **dans les
  deux sens**, ce que le plan n'avait pas prévu : la gagner est un véto, la **perdre est un
  gain**. Sans cette symétrie, monter `conf` pour écarter le gratte-ciel pris pour une bulle
  page 44 (score 0,36, uniformité 0,13) aurait été refusé comme « bulle perdue ».
- **`--conf` / `--iou` sur `run_manga.py`.** Ils **exigent `--page`** — un seuil pour tout le
  tome appartient à `config.yaml`, où il est tracé — et **impliquent `--from detection`**.
  L'écriture n'a lieu que si l'arbitre l'accepte ; sinon le cache reste intact.
- **`regions.json` porte un bloc de provenance optionnel** (`conf_threshold`, `iou_threshold`,
  `motif`) : sans lui, une planche relancée est indistinguable des 149 autres et le réglage qui
  a marché est perdu au run suivant. **`FORMAT_VERSION` n'est pas incrémenté** — `load_regions`
  renvoie `None` sur écart de version, ce qui déclencherait la retraduction des 150 planches ;
  un champ de provenance ne touche pas au contrat de nombre et d'ordre. Un test le verrouille.

### Modifié

- **`checkpoints.invalider_textes()` remplace deux suppressions manuscrites.** Dès qu'une
  opération change le nombre de régions, `ocr.json`/`traduction.json`/`qa.json` doivent partir :
  `stage_cache_present` teste la **présence** d'un fichier, pas sa longueur, et la page
  garderait sinon un OCR de l'ancien découpage, silencieusement décalé. `terminologie.txt` est
  épargné — cache non bloquant, aligné sur rien — et c'est ce qui garde le coût d'une relance à
  un seul appel LLM.

### Mesuré

- **Page 147, la région qui fusionne un ballon et du texte libre : aucun seuil ne la sépare.**
  Vingt et un réglages de 0,10 à 0,75 donnent exactement les mêmes onze bulles. Les scores de
  la planche sont bimodaux — un à 0,024, onze au-dessus de 0,88 — il n'y a donc rien entre les
  deux à faire apparaître ou disparaître. Une inférence a suffi à l'établir.
- **Page 44 en revanche : `--conf 0.45` écarte le faux positif** (uniformité 0,13) sans perdre
  aucune des cinq vraies bulles, et l'arbitre l'accepte.

## [0.25.0] - 2026-08-15

**Une bulle vide se rattrape bulle à bulle, pas en rejouant ce qui vient d'échouer.** MINEUR :
nouveau bloc `manga.rattrapage` (actif par défaut). Aucune action requise ; le rattrapage ne se
déclenche qu'à la traduction, donc un `--from rendu` ne coûte toujours aucun appel.

Le retry de page rejoue la numérotation — **exactement ce qui vient d'échouer**. Sur le Vol.1,
les deux retries de page ont échoué comme leur premier essai. L'escalade doit changer de **forme
d'appel**, pas de température : une bulle, une réponse, aucun numéro à se tromper.

### Ajouté

- **Rattrapage unitaire des bulles laissées vides.** Une bulle dont la source porte du texte et
  dont la traduction est vide est retraduite seule, avec sa taille en contexte et l'interdiction
  explicite de numéroter. Coût mesuré sur le tome : **un appel court**.
- **Un registre de motifs propre à la réponse unitaire** (`vide`, `liste`, `japonais_residuel`,
  `disproportionnee`). Il en fallait un : `bulles_manquantes` déclarerait fautive toute réponse
  non numérotée, c'est-à-dire précisément la forme qu'on demande ici. Une réponse diagnostiquée
  est **rejetée**, jamais dessinée — une mauvaise réplique dans une bulle est pire qu'une bulle
  vide, qui est au moins signalée.
- **`RAPPORT.md` distingue les bulles rattrapées.** Elles ont été traduites *hors du contexte de
  leur planche* et méritent un œil même quand elles ont l'air correctes ; `qa.json` porte un
  champ `rattrapee` par bulle. Les rattrapages refusés ont leur propre section.

### Corrigé

- **Le déclencheur « source OCR non vide » était trop naïf.** Sur les deux bulles sans
  traduction du Vol.1, l'une a pour source `（）` — deux parenthèses vides. La rattraper aurait
  coûté un appel LLM pour faire inventer une réplique à partir de rien. `tokens._CJK` ne pouvait
  pas servir de garde : il couvre le bloc des formes pleine chasse, donc il déclare « du
  japonais » sur ces parenthèses. Un test dédié vérifie que la source doit porter un **kanji, un
  kana ou une lettre latine** — `・` et `ー` exclus, `manga-ocr` rendant les points de suspension
  en `ーー` sur des dizaines de bulles.

### Modifié

- **Au-delà de `max_par_page: 3`, on ne rattrape rien.** Ce n'est plus un trou dans une planche
  mais une planche ratée : la reprendre bulle par bulle serait une retraduction déguisée, au prix
  d'un appel par bulle et sans le contexte de planche qui fait la qualité de la traduction. Le
  rapport renvoie alors vers `--page N --from traduction`.

## [0.24.0] - 2026-08-14

**Plus un seul carré tofu, et un rapport qui cesse d'accuser le traducteur.** MINEUR : trois
clés nouvelles sous `manga.typeset` (`taille_min_absolue`, `aire_min_bulle`, `marqueur_vide`),
toutes à défaut actif. Aucune action requise ; `--from rendu` suffit à en profiter.

### Ajouté

- **Table de substitution des glyphes absents.** Aucune police de la chaîne ne couvre
  `・ ～ ！ ？ 「 」 ー ／` — vérifié sur les trois — et la planche sortait avec un carré. Quatre
  étapes, dans cet ordre : chaîne de polices → substitution des seuls caractères non couverts →
  **re-tentative de la chaîne** sur le texte normalisé (la substitution peut le ramener dans
  Comic Neue, donc dans le bon dessin) → suppression de ce qui reste.
  > Invariant testé sur huit formes de texte : `glyphes_manquants(police, sortie) == ""`. **On ne
  > dessine jamais un glyphe qu'on n'a pas**, donc la table n'a pas besoin d'être exhaustive.

  Ajouter une police CJK à la chaîne aurait été le pire correctif : `font_pour_texte` bascule
  **toute la bulle**, donc un seul point médian ferait passer une bulle entière du lettrage
  manga à une police CJK.
- **`taille_min_absolue: 8` — un plancher empruntable.** Quand la géométrie rend `taille_min`
  inatteignable, on descend plutôt que de déborder : un débordement fait **découper les lettres
  par le masque**, un corps plus petit reste entier. Mesuré sur le Vol.1 : 5 bulles lettrées
  entre 9 et 10 px, et **9 débordements ramenés à 2**. Une bulle saine n'y touche jamais — elle
  a trouvé sa taille à la première étape, et un test verrouille l'égalité au bit près.
- **`marqueur_vide: "…"`.** Une bulle rendue vierge est indistinguable d'un choix éditorial. Des
  points de suspension se lisent comme un silence dans une bulle de manga, donc la planche n'est
  pas trahie, et le trou devient repérable. Marquée **uniquement** si la source japonaise n'était
  pas vide : une bulle sans japonais est vide à bon droit.

### Corrigé

- **Le rapport conseillait « raccourcir la traduction » neuf fois et n'avait raison qu'une.**
  Les débordements sont désormais séparés en trois causes, dont deux désignent la **détection** :
  - `bulle_degeneree` — la région ne peut porter aucun mot, même au plus petit corps : elle
    n'est **pas lettrée** du tout, plutôt que d'y peindre des fragments de lettres.
  - `bulle_etroite` — le mot le plus long ne tient pas en largeur.
  - `texte_trop_long` — et là seulement, raccourcir est le bon correctif.

  **La mesure a corrigé le diagnostic que j'avais posé** : la page 80 bulle 4, désignée comme
  le cas type de « traduction trop verbeuse », a en réalité **4 px de largeur utilisable** pour
  258 lignes de masque. Aucun texte n'y tiendrait. Elle est dégénérée, pas bavarde.
- **`--page` hors bornes réécrivait quand même le tome.** `--page 999` ne traitait rien mais
  allait au bout : `RAPPORT.md` réécrit, CBZ réencodé — une faute de frappe passait pour un run
  réussi. Contrôle avant les deux balayages, sortie en échec, rien n'est touché.
- **Le seuil bi-lobé du rapport ignorait la configuration.** `_SEUIL_BILOBEE` était un littéral :
  changer `manga.detection.scission.seuil_suspect` modifiait ce qui est **scindé** sans changer
  ce que le rapport **annonce**, soit deux chiffres qui se contredisent dans le même run.
  `tools/mesurer_bulles.py` lisait déjà la config, lui.
- **La 2ᵉ passe de lettrage repartait du texte brut.** Le recalcul d'une bulle harmonisée
  ignorait la normalisation des glyphes — il aurait redessiné le tofu qu'on venait d'écarter.

## [0.23.0] - 2026-08-14

**Le glossaire apprend enfin les fautes du run en cours.** MINEUR : nouveau bloc
`manga.terminologie` (défaut actif, **aucun appel LLM**), le glossaire de l'œuvre peut
désormais être enrichi automatiquement en `interdits`. Aucune action requise.

Le forçage ne rattrape que ce qu'on lui a listé. Sur le run v0.21.0 du Vol.1, les `interdits`
contenaient les fautes du run **précédent** (`Aselam`, `Kruuteo`, `Kataphrakto`) et le tome en
a produit de **nouvelles** (`Libentina` ×4, `Libertaine`). `compter_variantes.py` annonçait
« 0 forme bannie » — exact, et trompeur : le mécanisme n'était pas cassé, **il n'était jamais
alimenté**. C'est cette boucle qui se ferme.

### Ajouté

- **Détection de dérive d'orthographe, purement lexicale.** Trois niveaux de preuve, et seule
  la preuve décide de ce qu'on en fait :
  - **T1 « ancrée »** — un `termes_source` japonais de l'entrée est dans l'OCR de la **même
    bulle** que la forme suspecte. Il n'y a rien à interpréter : la forme est bannie et
    **corrigée dans le run en cours**, via `enforce_force` inchangé — donc avec ses garde-fous
    d'élision et d'accord, plutôt qu'un second remplacement qui les réinventerait moins bien.
  - **T2 « dominance »** — le nom canonique domine le tome (≥ 5 occurrences et ≥ 3 × celles du
    candidat). Banni en fin de tome, appliqué au prochain `--from rendu`. Une forme majoritaire
    n'est pas une faute, c'est un choix de traduction.
  - **T3 « lexicale »** — proximité seule : signalée au rapport, **jamais écrite**.
  Mesuré sur le Vol.1 : les 5 occurrences de `Libentina`/`Libertaine` sont trouvées, **et rien
  d'autre** — sur 193 mots capitalisés candidats.
- **Les pluriels ne sont plus confondus avec des dérives.** `Kataphrakts` ×8 n'est pas une
  faute : le bannir remplacerait le pluriel par le singulier en pleine phrase. Le rapport
  propose un champ `pluriel:` à la place.

### Corrigé

- **Le rapport distinguait mal « désactivé » de « en panne ».** `terminologue` commenté dans
  `manga.modeles` produisait les mêmes zéros qu'un échec. Trois états explicites, et
  « 0 remplacement » dit désormais *pourquoi* — aucune forme bannie n'était présente.
- **`tools/compter_variantes.py` ne dit plus qu'une moitié de la vérité.** À « 0 forme bannie
  encore présente » s'ajoute la liste des formes que **personne n'a encore bannies**. L'outil
  reste en lecture seule.

### Modifié

- **Les dérives vont dans `interdits`, jamais dans `variantes`.** `variantes` est la clé de
  recherche de `glossary_build._find_any` : y déposer une faute ferait fusionner une future
  entrée légitime dans la mauvaise, silencieusement et durablement. Un test le verrouille.
- **Une vraie distance d'édition remplace le ratio de `difflib`.** À son seuil de 0,78, le
  ratio produisait sur ce tome **11 groupes dont 9 de bruit** — `Désolé ~ Désolée`,
  `Comte ~ Vicomte`, `Cibles ~ Cible`, `Mitsukage ~ Mitsukage-san`… Mais le correctif de fond
  n'est pas un meilleur seuil : c'est de ne comparer qu'aux **noms du glossaire**, jamais les
  mots entre eux — aucun de ces neuf groupes n'est même examiné.
- **Quatre gardes, chacune tuant une classe de faux positif** : longueur minimale de 5
  caractères (`Vers` est à distance 1 de « Mers » — limite assumée et testée), budget d'édition
  proportionnel (1 jusqu'à 7 caractères, 2 au-delà : **`Avion`/`Areion` = 2 sur 6 est rejeté
  délibérément**, car tout réglage qui l'attrape rattrape aussi « Les » → « Vers »), garde de
  pluriel, et capitale exigée en milieu de phrase pour T3.
- **Le lexique des têtes de phrase et le comptage à frontières de mot** quittent
  `tools/compter_variantes.py` pour `manga/terminology.py`, que l'outil importe — la mesure et
  le pipeline ne peuvent plus diverger.

## [0.22.0] - 2026-08-14

**Plus jamais un numéro dessiné dans une bulle.** MINEUR : `qa.json` gagne un champ
`strategie_traduction` et `RAPPORT.md` deux sections. Aucune action requise ; les caches
restent valides et `--from rendu` suffit à relettrer un tome déjà traduit.

Sur le Vol.1 du *manga A*, **9 bulles de la page 129** portaient un
« 1. », « 2. »… lettré à l'encre. Le modèle avait rendu 9 répliques pour 10 bulles ; le
test tout-ou-rien `len(numbered) >= n` basculait alors la planche **entière** dans le repli
positionnel — lequel recopiait la ligne telle quelle, préfixe compris.

### Corrigé

- **Le repli positionnel ne retire plus seulement les numéros : il n'est presque plus
  atteint.** `repliques_par_bulle` honore désormais les numéros **présents** et laisse les
  autres bulles vides (*mapping partiel*), au lieu de tout abandonner à l'ordre des lignes
  dès qu'il en manque un. Une bulle vide est signalée par le rapport ; un numéro dessiné,
  non. Le repli ne sert plus que si le modèle n'a numéroté **aucune** ligne.
- **Le préfixe numéroté est retiré partout**, repli compris, et jusqu'au préfixe redoublé
  (« 1. 1. Texte »). Invariant testé sur sept formes de sortie : aucune réplique rendue ne
  commence par un numéro.
- **Les caches déjà produits sont réparés à la lecture.** `traduction.json` contient le
  préfixe tel qu'il a été analysé : corriger l'analyse seule aurait imposé de **retraduire**
  chaque planche touchée. `load_traduction` retire le préfixe, donc un `--from rendu` répare
  le tome entier sans un seul appel LLM.
- **Un millésime n'est plus pris pour un numéro de liste.** La page 8 du même tome contient
  une bulle de récitatif « 1972... » : l'expression d'origine y lisait la réplique n° 1972
  suivie de « .. », et le retrait du préfixe l'aurait réduite à deux points. Le séparateur
  doit désormais être suivi d'une espace, et le nombre doit pouvoir être un index de bulle.
- **Une ligne non numérotée qui suit une réplique lui est recollée.** L'ancien code la
  jetait : une réplique coupée en deux perdait sa seconde moitié.
- **Un « 11. » sur 10 bulles est du bruit**, plus une réplique — il faussait le décompte
  qui décide du retry. Sur un numéro en double, le **premier** gagne.
- **`--from rendu` n'efface plus le diagnostic de la traduction qu'il réutilise.** Le motif
  d'échec n'étant pas recalculable sans la sortie brute du modèle, il était réécrit à
  `null` dans `qa.json` à chaque relettrage : le rapport annonçait « 0 échec » sur un tome
  inchangé. Motif et stratégie sont désormais repris du `qa.json` précédent.

### Modifié

- **La numérotation n'est plus lue à deux endroits.** `quality_manga._LIGNE_NUM` (le
  diagnostic) et `orchestrator_manga._NUM_LINE_RE` (la reconstruction) étaient deux
  expressions régulières jumelles, libres de diverger — alors que la première décide de
  retenter et la seconde de ce qui sera dessiné. Tout passe par
  `quality_manga.analyser_numerotation()` et son objet `Numerotation` (répliques bornées,
  préambule, hors-bornes, doublons) ; `_parse_translations` n'est plus qu'un délégué d'une
  ligne.
- **`RAPPORT.md` dit comment chaque planche a été rattachée.** Deux sections nouvelles —
  « rattachées SANS numérotation » (le seul cas où une réplique peut atterrir dans la
  mauvaise bulle) et « numérotation incomplète » — plus une ligne de résumé. Le rendu d'une
  planche reconstituée positionnellement est indiscernable à l'œil d'une planche numérotée ;
  rien ne les distinguait jusqu'ici.
- **Avertissement de run** quand une planche part en repli positionnel, distinct du motif
  `bulles_manquantes` : l'un signale des trous, l'autre un alignement non garanti.

## [0.21.0] - 2026-08-14

**Photoshop ne plante plus, et les calques de texte repassent en option.** MINEUR :
nouveau drapeau `--psd-test`, et le défaut de `manga.rendu.psd_texte` passe à
`"rasterise"`. Aucune action requise — une relance produit simplement un PSD sûr.

La v0.19.1 avait corrigé l'alerte « Problèmes à la lecture des calques » ; elle a
**introduit un plantage à l'ouverture**, ce qui est pire. Retour à un défaut sûr, plus
les deux correctifs de fond.

### Corrigé

- **Le descripteur `Txt ` et l'`EngineData` annonçaient des longueurs différentes.** La
  v0.19.1 ajoutait le retour chariot terminal à l'`EngineData` seule : `Txt ` déclarait
  7 caractères là où les passes de style en couvraient 8. Photoshop dimensionne ses
  tampons sur `Txt ` puis y écrit selon les passes — dépassement, plantage à l'ouverture,
  sans même la boîte d'alerte. Les deux passent désormais par `texte_moteur()`, et un test
  vérifie l'égalité stricte des longueurs vues par un lecteur tiers.
- **L'`EngineData` était trop pauvre pour rendre le texte éditable.** Photopea affichait
  les calques sans jamais les rouvrir à l'outil Texte. Feuille de style portée de 5 à
  **34 clés** et propriétés de paragraphe de 1 à **21** (les défauts d'Adobe), plus les
  blocs `/Rendered`, `/AntiAlias`, `/UseFractionalGlyphWidths` et les tailles
  d'exposant/indice/petites capitales du `ResourceDict`.

### Modifié

- **`manga.rendu.psd_texte` vaut maintenant `"rasterise"` par défaut**, et `"type"` est
  documenté comme EXPÉRIMENTAL. Deux tentatives ont échoué sur cette machine (alerte puis
  dégradation en pixels, puis plantage) et **aucun Photoshop n'est disponible ici** pour
  valider la troisième. Un fichier qui fait planter Photoshop est pire qu'un fichier non
  réécrivable : le lettrage rasterisé reste exact, seule la frappe au clavier manque.

### Ajouté

- `run_manga.py --psd-test [FICHIER]` écrit un PSD **minimal** — un fond, un seul calque
  de texte « Test » — et rappelle quoi vérifier. Valider les calques de type coûtait
  jusqu'ici un run complet et, quand ça tournait mal, un Photoshop qui plante ; le cycle
  « écrire → ouvrir → constater » descend à dix secondes, et isole la question : si ce
  fichier passe, le `TySh` est bon et un échec vient d'ailleurs.

## [0.20.0] - 2026-08-14

**Le détecteur de bulles se télécharge tout seul.** MINEUR : nouvelle capacité, deux clés
de config optionnelles, aucun comportement changé quand le modèle est déjà là.

Le fichier `manga_models/bubble_detector.onnx` (~104 Mo) n'est pas dans le dépôt — il est
dans `.gitignore` depuis le lot 0. `manga-ocr` récupérait le sien automatiquement ; celui
du détecteur exigeait un `Invoke-WebRequest` recopié à la main. Le jour où il disparaît
(machine neuve, nettoyage, dossier synchronisé qui évince 104 Mo), le pipeline s'arrêtait
net à la première planche sur une consigne à exécuter soi-même.

### Ajouté

- `manga/models.py` : récupération automatique des poids, sur `urllib.request` de la
  bibliothèque standard — aucune dépendance ajoutée, comme `struct` suffit à écrire un PSD.
  L'écriture passe par un fichier `.part` renommé **seulement** une fois la taille attendue
  atteinte : une coupure réseau, un Ctrl+C ou un disque plein ne laissent jamais un `.onnx`
  tronqué qu'ONNX Runtime refuserait ensuite à chaque relance, sans que rien n'indique
  qu'il suffit de le supprimer. L'avancement passe par le reporter — 104 Mo en silence
  ressemblent à un pipeline planté — et atterrit donc aussi dans `perf.log`.
- `manga.detection.telechargement_auto` (défaut `true`) et `manga.detection.model_url`
  (vide = le modèle de `manga_models/README.md`). `telechargement_auto: false` restaure le
  message actionnable et l'arrêt.
- `run_manga.py --check` **récupère** le modèle au lieu de signaler son absence : c'est le
  moment où l'on prépare la machine, pas au milieu d'un tome de 150 planches.
- Taille et empreinte SHA-256 du modèle de référence documentées dans
  `manga_models/README.md`. Un écart est signalé sans bloquer : un dépôt amont qui
  republie ses poids ne doit pas arrêter le pipeline.

### Corrigé

- `test_verbose_reports_per_stage_timing_and_speed` cherchait la sous-chaîne
  `[traduction]` pour vérifier l'absence d'une ligne de **chrono**. Or en dry-run la
  « traduction » est le texte OCR japonais : le garde-fou `japonais_residuel` émet donc un
  avertissement `⚠ [traduction] page 1 : …` parfaitement légitime, et l'assertion échouait.
  Le défaut ne se voyait pas parce que ce test est sauté quand les poids du détecteur
  manquent — c'est-à-dire, jusqu'ici, sur toute machine qui ne les avait pas téléchargés à
  la main. La suite passe désormais **945 tests, zéro sauté**.

## [0.19.1] - 2026-08-14

**Les PSD s'ouvrent enfin dans Photoshop avec des calques de texte éditables.** CORRECTIF :
aucun changement d'interface, aucun changement de rendu — le composite reste identique
pixel pour pixel à `pages_out/`. Les PSD déjà produits se régénèrent avec
`--from rendu`, sans OCR ni appel LLM.

Photoshop affichait « Problèmes à la lecture des calques […] en raison d'une erreur du
programme. Certains calques utiliseront les données de pixel existantes », puis dégradait
chaque `Texte NN` en calque de pixels. Les calques **étaient** bien de type : c'est leur
bloc `TySh` qui était illisible, et Photoshop appliquait le repli documenté.

### Corrigé

- **`_descripteur` n'écrivait pas son identifiant de classe** (`manga/psd.py`). Un
  descripteur PSD porte un `classID` de **4 octets même quand sa longueur déclarée vaut
  0** — c'est la convention du format, pas une absence. En l'omettant, le lecteur prenait
  le *nombre d'items* pour l'identifiant, lisait ensuite « 0 item », et le descripteur de
  texte ressortait vide : ni `Txt `, ni `bounds`, ni `EngineData`. Cause racine de
  l'alerte, et elle touchait **tous** les descripteurs du fichier (texte, `bounds`,
  `boundingBox`, déformation).
- **La marque d'ordre des chaînes du moteur de texte s'écrivait en échappements octaux**
  (`\376\377`) dans le `/Name` des feuilles de style. Un lecteur ne reconnaît une chaîne
  UTF-16 qu'à la séquence d'octets **bruts** `(\xfe\xff` ; sans elle il découpe aux
  espaces, et « Normal RGB » cassait toute l'`EngineData`.
- **`ParagraphRun` déclarait un seul paragraphe** couvrant tout le texte, quel que soit le
  nombre de retours. Le moteur veut une entrée de `RunArray` **par paragraphe** et un
  `RunLengthArray` de même cardinalité, terminateur `\r` final compris. Toute bulle de
  plus d'une ligne — donc la quasi-totalité — était concernée.
- **Un bloc `8BIM` déclarait sa longueur brute** au lieu de la longueur arrondie au
  multiple de 2, faisant repartir un lecteur un octet trop tôt sur des données de taille
  impaire. Latent jusqu'ici : les `TySh` produits tombaient sur des tailles paires.
- `_v_enum` écrit désormais les identifiants de 4 caractères sur une longueur de 0, seule
  forme que Photoshop produit lui-même.

### Ajouté

- `requirements-dev.txt` et `tests/test_manga_psd_relecture.py` : les PSD sont relus par
  **`psd-tools`**, un lecteur indépendant. C'est le correctif de fond — l'analyseur maison
  de `tests/test_manga_psd.py` partage les hypothèses de l'écrivain et avait donc reproduit
  fidèlement le descripteur mal formé au lieu de le signaler. Dépendance de **test
  seulement** : l'écriture reste en `struct` de la bibliothèque standard.
- `RAPPORT.md` et `run_manga.py --check` nomment la ou les polices PostScript déclarées par
  les calques de type. Photoshop **substitue en silence** une police absente du système :
  le calque reste éditable, mais le lettrage change sans explication.

### Modifié

- `tests/test_manga_psd.py::test_l_engine_data_declare_la_bonne_longueur_de_texte`
  affirmait `[ len(texte) ]` deux fois — l'hypothèse fausse qui avait laissé passer le bug.

## [0.19.0] - 2026-08-14

**Les light novels lisent des sources `.epub`.** MINEUR : nouveau format d'entrée, aucune
dépendance ajoutée, aucun comportement changé sur les `.docx`/`.pdf`/`.txt`/`.md`. La brique
manga n'est pas touchée.

Déposer un `.epub` dans `sources/<Projet>/<Tome>/<LANGUE>/` suffit — c'est le cas de
`sources/roman A/Vol.1/JAP/`, qui a servi de référence.

### Pourquoi un module dédié plutôt que Pandoc

Pandoc lit les EPUB et il est **déjà requis** pour les `.docx` : c'était le premier réflexe. Il
est disqualifié à la mesure, sur le livre réel (light novel japonais, 33 documents) :

| | Pandoc | `pipeline/epub.py` |
|---|---|---|
| texte extrait | 2 578 904 car. | **176 208 car.** |
| images utilisables | 7 sur 23 | **23** |
| durée | 9,1 s | **0,4 s** |

Trois causes, toutes rédhibitoires :

1. **16 illustrations sur 23 disparaissent.** Le livre est en mise en page fixe : ses pleines
   pages sont des `<svg><image xlink:href="…"/></svg>`, que Pandoc recopie en HTML brut au lieu
   d'émettre un lien d'image. Le marqueur `<!-- IMG: … -->` du pipeline ne les voit donc pas.
2. **Le texte est noyé.** L'EPUB est passé par la chaîne Kobo, qui enveloppe **chaque phrase**
   dans un `<span class="koboSpan" id="kobo.N.M">` — ~24 000 spans, rendus par Pandoc en
   attributs Markdown.
3. **Les furigana sont collés au texte.** `<ruby>七堕<rt>ナナエ</rt></ruby>` ressort `七堕ナナエ`.
   Sur 8 140 ruby, la source japonaise transmise au traducteur est corrompue de bout en bout.

### `pipeline/epub.py` — 422 lignes, `zipfile` + `html.parser`

Un EPUB est **déjà structuré**, à l'inverse d'un PDF : il n'y a presque rien à deviner.

- **Ordre de lecture** = celui du `spine` de l'OPF, jamais celui du zip (qui, sur ce livre,
  commence par la quatrième de couverture) ni l'ordre alphabétique. L'OPF lui-même est **lu**
  dans `META-INF/container.xml`, jamais deviné : son chemin varie d'un producteur à l'autre.
- **Furigana** retirés par défaut, ou conservés en `七堕(ナナエ)` avec
  `decoupage.epub.ruby: "parentheses"` — utile pour faire *relever les lectures* des noms
  propres par le terminologue, exactement l'information qui manquait au manga. Les garder gonfle
  la source de 30 % (176 208 → 228 967 caractères, mesuré), d'où le défaut à `"ignorer"`.
- **Titres**, par ordre de préférence : une vraie balise `<h1>`…`<h6>` ; sinon l'intitulé de la
  table des matières qui pointe sur le document (`nav` EPUB 3 **et** `toc.ncx` EPUB 2) ; sinon
  sa **première ligne courte** suivie de texte. Ce dernier cas est celui de ce livre, dont les
  chapitres s'ouvrent sur un `一` ou un `序` posé dans un `<p class="font-1em30 bold">` — un
  paragraphe *stylé*, pas un titre, et la feuille de style de l'EPUB **ne définit même pas cette
  classe** : la détection par police+gras des chemins PDF et DOCX n'avait rien à mesurer.
  Un document sans titre retenu n'ouvre pas de chapitre, sinon chaque page d'illustration en
  deviendrait un.
- Résultat sur le livre réel : **13 chapitres** correctement nommés (`序`, `一`, `二`, `三`, `四`,
  `終`, `あとがき（スタッフロール風）`, `終ノ二、あるいは真なる序`…), et un `--dry-run` complet qui
  produit les trois rendus avec **23 images sur 23** dans la sortie.

### Le piège du japonais, et sa symétrie latine

`<span>`, `<ruby>`, `<a>` sont des éléments **inline** : joindre leur contenu par une espace
donne `千 万 丈 塔` au lieu de `千万丈塔`. Le japonais ne sépare pas ses mots — une espace insérée
à tort n'est pas une coquille de mise en forme, c'est une **erreur de segmentation** qui se
propage jusqu'au glossaire. Seuls les éléments de bloc et `<br/>` coupent une ligne.

Symétriquement, le **saut de ligne du fichier source** (l'indentation du XHTML) ne peut pas être
traité uniformément : il vaut **une espace** entre deux lettres latines — sinon un EPUB anglais
replié à 80 colonnes donnerait `theenemy` — et **rien** entre deux caractères CJK. C'est la règle
des navigateurs (« segment break transformation rules » de CSS Text), et les deux moitiés sont
verrouillées par des tests. Le saut est donc *marqué* pendant l'analyse et résolu à la clôture de
la ligne, quand on connaît enfin ses voisins.

### Tests

`tests/test_epub.py` (35 tests) fabrique ses EPUB **à la main**, avec les particularités réelles :
spans Kobo, furigana, illustrations en SVG, chapitre ouvert par un paragraphe stylé, OPF ailleurs
que dans `OEBPS/`, spine dans un ordre **différent** de celui du zip. Sont verrouillés notamment :
aucune espace ASCII insérée dans du japonais ; l'espace *conservée* entre deux mots latins ; un
`<ruby>` à plusieurs couples base/lecture apparié correctement ; `<rp>` toujours retiré ; le
document de navigation jamais recopié en texte ; une image réutilisée écrite une seule fois ;
`extract_images=False` n'écrit rien et ne laisse aucun marqueur ; un titre doit être court
**relativement à son corps**. Un test lit l'EPUB réel et se saute si les sources sont absentes
(elles ne sont pas versionnées).

Suite complète : **902 tests**.

### Trois défauts corrigés en chemin

**`<rp>` fuyait en mode `"parentheses"`.** Un compteur unique pour `<rt>` et `<rp>` faisait sortir
`七堕（(ナナエ)）` : `<rp>` n'est qu'une parenthèse de repli pour les lecteurs sans ruby et doit
disparaître dans les **deux** modes. Compteurs séparés.

**Un test qui ne prouvait rien.** `test_les_documents_suivent_lordre_du_SPINE_pas_celui_du_zip`
écrivait le zip et déclarait le spine dans le **même** ordre : il aurait passé avec un lecteur
qui suit le zip. Le fabricant d'EPUB de test accepte désormais un ordre de spine distinct.

**Trois tests de `test_sources.py` cassés par un paramètre.** Leurs doubles de `extract.extract`
déclaraient la signature exacte ; ajouter `epub_cfg` les cassait alors qu'ils ne parlent pas
d'EPUB. Ils acceptent maintenant `**_` — le prochain format n'en cassera aucun.

### Une observation hors périmètre, documentée

En vérifiant le bout en bout j'ai constaté qu'**un `--dry-run` écrit dans les checkpoints**, et
que ce qu'il y écrit est le texte **source** — c'est la définition du dry-run, chaque agent
renvoyant son `dry_payload`. Un run réel lancé ensuite sur le même Tome réutilise ce cache et
produit un tome **non traduit, sans rien signaler**. Le README recommandait le dry-run sans le
dire ; il porte maintenant l'avertissement et le remède (`--force`, ou supprimer
`.checkpoints/`). Comportement inchangé : ce n'est pas le périmètre de ce lot.

## [0.18.0] - 2026-08-14

**Lot 4.4 — export PSD à calques : retoucher une planche dans Photoshop.** MINEUR : nouveau
format de sortie, **désactivé par défaut**. Rien ne change si `"psd"` n'est pas dans
`manga.rendu.formats`. Aucune dépendance ajoutée, aucun cache invalidé. Le light novel n'est pas
touché. **Fin du lot 4.**

### Le manque

`manga.rendu.formats` ne produisait que des sorties **aplaties** : corriger une réplique
imposait de relancer le pipeline, et rien ne permettait de déplacer un bloc de texte de trois
pixels. Or `typeset._draw_fit` construisait déjà, par bulle, exactement ce qu'un calque
demande — un calque RGBA, un rectangle, une transparence — puis l'aplatissait et le jetait.
`qa.json` n'en gardait qu'une taille et un *nombre* de lignes : ni les lignes, ni `top`, ni
`center_x`, ni `line_h`, ni la police résolue, ni la couleur.

### Ce qui a été ajouté

- `manga/typeset.py` — `calque_fit`, extrait de `_draw_fit` : le calque RGBA d'une bulle, déjà
  découpé au masque, avec son décalage. Un calque rasterisé d'un PSD est donc **pixel pour
  pixel** ce que la planche aplatie contient. Et `typeset_page(fits_out=…)`, qui expose la
  recette de lettrage finale (après harmonisation de planche) — même idiome que `report_out` ici
  et que `styles_out` dans `clean.py`.
- `manga/psd.py` — l'écrivain PSD, **en Python pur** : `struct` et `zlib` de la bibliothèque
  standard, plus numpy déjà présent. `psd-tools` est orienté lecture et `pytoshop` n'est plus
  maintenu ; c'est la même logique que `requirements-manga.txt` refusant OpenCV pour trois
  opérations de morphologie. Calques en ZIP, aperçu aplati en RLE (PackBits), bloc `luni` pour
  les noms accentués, bloc de résolution.
- `manga/orchestrator_manga.py` — écriture **dans la boucle** de rendu et non dans
  `assemble_outputs`, qui ne voit que des pages finies et n'a pas les `Fit`. C'est un format
  « dossier de pages », comme `"images"`.
- `config.yaml` — `"psd"` dans `manga.rendu.formats`, plus `psd_texte` (`"type"` /
  `"rasterise"`) et `psd_original`.
- `README.md` §12, sous-section « Retoucher une planche dans Photoshop ».

### Calques de type réels

Chaque bulle devient un vrai **calque de texte** Photoshop : bloc `TySh` avec la matrice de
transformation, le descripteur de texte et l'`EngineData` — le moteur de texte, où sont écrits
la police, le corps, l'interligne, la couleur et la justification. Un double-clic avec l'outil
Texte et la réplique se réécrit.

Deux pièges traités explicitement :

- **La ligne de base.** `_draw_fit` dessine avec `anchor="ma"`, donc `fit.top` est le haut de
  l'ascendante, alors qu'un calque de type se positionne sur la **ligne de base**. Confondre les
  deux décalerait tout le texte d'une ascendante entière. Un test le verrouille.
- **Une bulle en débordement retombe en rasterisé.** Sa mise en page n'est plus celle qu'un
  calque de type saurait reproduire : mieux vaut des pixels justes qu'un calque éditable faux.

### Poids et coût, mesurés

Sur une planche réelle de 1125×1600 à 12 bulles : **7,2 Mo** — 2,4 Mo pour le scan d'origine,
2,0 Mo pour la planche nettoyée, ~2,7 Mo pour l'aperçu aplati, et **0,01 Mo pour les douze
calques de texte réunis**, chacun étant borné à sa bulle. Soit ~1,1 Go pour un tome de 150
planches, ~700 Mo avec `psd_original: false`. Le rendu d'une planche passe de ~0,3 s à ~2,4 s.

### Ce qui est vérifié, et ce qui ne l'est pas

`tests/test_manga_psd.py` (35 tests) embarque un **analyseur PSD indépendant de l'écrivain** :
on ne teste pas un format binaire en regardant le résultat. Sont vérifiés sur le fichier
réellement écrit — en-tête, nombre et noms de calques (dont le `luni` accentué), rectangles,
quatre canaux par calque, aller-retour PackBits sur huit cas limites, **aperçu aplati identique
au pixel** à la planche rendue, calque de fond identique au pixel à `pages_clean/`, présence du
`TySh` en mode type et son absence en mode rasterisé, pixels **identiques** entre les deux modes,
chaîne française retrouvée en UTF-16BE dans l'`EngineData`, longueur de `RunLengthArray`
cohérente avec le texte, lignes jointes par `\r` et non `\n`, ligne de base = `top + ascendante`,
et le câblage complet dans l'orchestrateur. Vérifié aussi sur la planche 40 du tome réel : 14
calques, relecture sans erreur, composite identique à `pages_out/`.

**En revanche, aucun Photoshop n'a ouvert ces fichiers** — il n'y en a pas sur cette machine.
Le risque est borné par le format : un calque de type porte **aussi** ses pixels, donc si
Photoshop refusait son moteur de texte, le calque se comporterait comme un rasterisé et on ne
perdrait que la réécriture au clavier. `psd_texte: "rasterise"` le coupe entièrement.

### Deux défauts trouvés en chemin

**`typeset_page` mute l'image qu'on lui passe.** Sans copie, le calque « Planche nettoyée » du
PSD aurait contenu la planche **déjà lettrée** — le letteur aurait repeint par-dessus le texte.
Un test le verrouille.

**PackBits produisait un octet hors plage.** Découper une plage de 129 octets identiques en
128 + 1 laissait un reliquat de 1, dont l'en-tête `257 − 1` vaut 256. Le bloc est maintenant
rogné pour que le reliquat soit nul ou ≥ 3. Trouvé par le test d'aller-retour, pas par hasard.

Suite complète : **867 tests**.

## [0.17.0] - 2026-08-14

**Lot 4.3 — le bloc de texte peut quitter le centre vertical de la bulle.** MINEUR : nouvelle
clé `manga.typeset.glissement_vertical`, dont le défaut (0,5) **change le rendu** — donc pas un
correctif au sens de la règle de numérotation. Aucun cache n'est invalidé : un `--from rendu`
suffit, sans un seul appel LLM. Le light novel n'est pas touché.

### Le défaut

La largeur disponible d'une ligne est le **minimum** du profil de masque sur toute sa hauteur —
c'est ce `min` qui empêche le texte de déborder dans les coins arrondis, et il n'est pas
négociable. Mais `layout_at_size` n'essayait qu'**une seule** position verticale, le bloc centré
sur l'étendue utile. Dans une bulle dentelée, en sablier ou simplement asymétrique, ce bloc
tombe donc sur le passage le plus étroit alors que 30 px plus haut il aurait deux fois la place.

C'est la deuxième cause du symptôme « texte minuscule dans une grande bulle », indépendante des
bulles doubles du lot 4.2 : sur les 28 bulles composées à ≤ 13 px dans une boîte de plus de
20 000 px², **9 seulement** étaient bi-lobées. Page 40, `« Eeeeeh~~~ »` — neuf signes — était
dessiné à 11 px et **signalé en débordement** dans une bulle de 136×213 px.

### Le correctif, et la garantie de non-régression

`layout_at_size` accepte `glissement`, la fraction de l'espace libre dont le bloc peut s'écarter
du centre. Cinq positions sont essayées, **le centre en premier**, et celle qui maximise la
largeur disponible la plus faible est retenue — à égalité le centre gagne, parce que le texte
d'une bulle doit rester centré quand rien ne l'y oblige.

`best_fit` lance la dichotomie **deux fois** (bloc centré, puis bloc glissant) et garde la
**plus grande** des deux tailles. Cette composition n'est pas de la prudence décorative : sans
elle, 2 bulles sur 199 rétrécissaient — page 48, 25 → 20 px. Autoriser le glissement fait monter
la plus grande taille qui tienne, ce qui ouvre d'autant la fenêtre de `_affiner_qualite`
(28 % sous la taille maximale), laquelle peut alors descendre plus bas qu'avant en chassant les
lignes orphelines. Prendre le maximum rend la régression impossible **par construction**, au
prix d'une seconde dichotomie (~6 essais ; le lettrage coûte ~0,3 s par planche).

L'échelle de replis anti-débordement glisse aussi : à ce stade la seule alternative est de
dessiner à `taille_min` et de signaler.

### Mesuré sur les 792 bulles du tome de référence

| | |
|---|---|
| bulles plus grandes | **219** (28 %), médiane **+2 px**, maximum **+19 px** |
| bulles plus petites | **0** |
| débordements | **14 → 12** |
| police médiane de la planche | 24 px, inchangée |

Plus gros gains : page 88 bulle 3, 36 → 55 px ; page 22 bulle 13, 35 → 52 ; page 98 bulle 4,
20 → 34 ; page 118 bulle 1, 30 → 44. Les deux débordements résolus (page 40 bulle 8, page 130
bulle 1) passent de 11 à 19 px. Contrôle visuel de la page 40 avant/après : six bulles
nettement plus lisibles, aucune sortie de masque, aucun texte visiblement décentré.

Cinq positions suffisent : passer à neuf et au glissement libre n'ajoute que 7 bulles gagnantes
et 1 px de gain médian.

### Tests

`tests/test_manga_typeset.py` passe de 45 à 55 tests. Ce qui est verrouillé :
`glissement_vertical: 0` rend **exactement** l'ancien lettrage (même `top`, mêmes lignes, mêmes
largeurs) ; le glissement ne rétrécit **jamais** une bulle, sur deux géométries × six textes ;
le centre l'emporte à égalité (dans un rectangle, le bloc reste centré) ; le texte ne sort
toujours pas du masque, sur cinq textes dont `"A" * 120` ; le glissement ne crée pas de
débordement. Suite complète : **832 tests**.

## [0.16.0] - 2026-08-14

**Lot 4.2 — bulles doubles : une région pour deux ballons.** MINEUR malgré le passage de
`manga/checkpoints.py:FORMAT_VERSION` à **v3** : la migration est automatique, se fait **sans
le modèle ONNX**, et n'invalide le cache que là où il était faux. Le light novel n'est pas
touché (aucune ligne de `core/` ni de `pipeline/`).

### Le défaut

Le détecteur émet parfois **une** instance là où le dessinateur a mis **deux** ballons qui se
touchent : 5 régions pour 6 ballons page 136 du *manga A* Vol.1, 8 pour 9
page 142. Tout le reste de la chaîne se comportait alors correctement, ce qui rendait le défaut
invisible : une chaîne OCR pour la région (`敵機２時方向！いいよ転校生！！` — deux locuteurs), une
réplique traduite (« Avion ennemi à deux heures ! Allez, nouvelle élève !! »), un bloc de texte.

Le lettrage s'effondrait pour une raison précise et mesurable. `clean._centre_x` place l'axe du
texte au centroïde de **l'ensemble** du masque, donc dans le vide entre les lobes ; le profil de
largeur *symétrique* de `typeset._profil` ne garde alors de la place qu'au **goulot** ; et
`layout_at_size` centre le bloc verticalement sur toute l'étendue utile, ce qui le pose
précisément dessus. La largeur utilisable médiane, qui décide de la taille de police :

| | remplissage du masque | largeur utilisable médiane | police |
|---|---|---|---|
| page 136 bulle 5, fusionnée | 0,606 | **32 px** | **13 px** |
| → lobe 1 / lobe 2 | | 150 / 136 px | |
| page 142 bulle 1, fusionnée | 0,616 | **76 px** | **13 px** |
| → lobe 1 / lobe 2 | | 175 / 182 px | |
| page 64 bulle 4, fusionnée | 0,556 | **31 px** | **11 px** |
| → lobe 1 / lobe 2 | | 126 / 144 px | |

**Rien ne le signalait** : autant de traductions que de bulles donc pas d'écart de comptage, le
texte tenait donc pas de débordement — ni la page 136 ni la page 142 n'apparaissaient dans
`RAPPORT.md`. Les deux métriques qui l'auraient attrapé, remplissage du masque et dérive du
centroïde, n'étaient calculées **nulle part**.

### Ce qui a été ajouté

- `manga/geometry.py` — `remplissage`, `composantes` (étiquetage par plages de lignes +
  union-find, numpy pur, 4-connexité) et `scinder_par_erosion`. La séparation se fait par
  **échelle d'érosion** : c'est le goulot qui cède le premier, et il vaut le recouvrement
  horizontal des deux ballons (46 px page 136, 87 px page 142, contre des lobes de 150 à
  215 px). Une coupe droite en ligne ou en colonne échouerait, le goulot étant parfois **plus
  large** que chaque lobe (266 px page 136 : les deux ballons y sont présents ensemble).
- `manga/bubbles_split.py` — la décision, appliquée **avant l'ordre de lecture** donc avant
  l'OCR, pour que chaque ballon reçoive son propre texte.
- `manga/detection.py` — `BubbleRegion.scindee`, persisté dans `regions.json` : c'est ce qui
  permet à `RAPPORT.md` de décrire le **tome** et non le run.
- `manga/report_manga.py` — deux sections neuves, « Bulles issues d'une région bi-lobée
  scindée » et « Régions bi-lobées SUSPECTES, non scindées », plus `remplissage_masque` par
  bulle dans `qa.json`.
- `tools/mesurer_bulles.py` — la distribution géométrique d'un tome, et `--scindables` pour
  voir ce que la configuration appliquerait sans rien écrire.
- `config.yaml > manga.detection.scission` — quatre seuils, chacun documenté avec le chiffre
  qui l'a fixé.

### Les seuils viennent d'une mesure, pas d'une intuition

Les 797 bulles du tome ont été passées avec une validation minimale, et les **40 découpages
obtenus inspectés un par un sur le dessin**. Les huit faux — une bulle unique tranchée en deux
(pages 80 et 134), un fragment de kanji pris pour une bulle (page 33), une onomatopée sur de la
trame (page 84) — ont tous un **remplissage de lobe ≤ 0,71**, là où les vrais doubles montent à
0,72-0,91. C'est ce seul critère qui décide.

Le réglage est délibérément **conservateur**, parce que les deux erreurs ne coûtent pas la même
chose : scinder à tort casse une planche correcte (deux OCR partiels du même ballon, deux blocs
dans ses deux moitiés), alors que ne pas scinder laisse simplement le défaut en place. Résultat
sur le tome : **19 scissions sur 18 planches, zéro faux positif**, au prix d'une douzaine de
vrais doubles manqués (remplissage 0,57 à 0,71) — ceux-là sont listés comme suspects.

Effet vérifié sur le lettrage, en imposant à chaque lobe la réplique **entière** (borne
pessimiste : après scission il n'en recevra que la moitié) : sur les **8 bulles visiblement
cassées** (police ≤ 14 px), aucune ne régresse et la médiane passe de 12 à 14,5 px ; sur les
deux planches témoins, 13 px → 20-23 px page 136 et 14 → 17-19 px page 142. Avec le texte
réellement partagé, page 136 monte à 24 et 35 px.

### Migration du cache — sans le modèle ONNX

La scission est un post-traitement de **masques** : `checkpoints.migrate_page` l'applique donc
aux masques déjà en cache, et un tome se migre sans avoir à re-détecter (le
`manga_models/bubble_detector.onnx` n'est pas requis). Mais une planche qui gagne des bulles
perd `ocr.json`, `traduction.json` et `qa.json` : leur alignement **par position** est
irrécupérable, et la chaîne fusionnée portait deux répliques. C'est le seul endroit du projet
qui jette du travail déjà payé, et c'est assumé.

Vérifié sur une **copie** du cache réel (150 planches) : 18 planches gagnent des bulles et
perdent leur OCR, **132 gardent tout**, 797 → 816 régions, et l'assertion « seules les planches
scindées perdent leur cache » tient. Le cache de l'utilisateur n'a pas été migré ici : Ollama
étant injoignable, les 18 planches n'auraient pas pu être retraduites.

### Un défaut latent trouvé en chemin

« Page déjà entièrement générée » se jugeait sur la seule existence de `pages_out/page_XXXX.png`.
Une planche dont un cache amont avait disparu était donc **sautée sans être réparée** — et,
avec cette migration, elle aurait été sautée juste après avoir été invalidée. Le raccourci exige
maintenant que `stages_to_redo` ne contienne rien d'autre que `rendu`.

Deux outils affichaient du japonais ou des flèches sans configurer stdout en UTF-8 :
`tools/compter_variantes.py` et le nouveau `tools/mesurer_bulles.py` levaient
`UnicodeEncodeError` sur une console Windows en cp1252, après avoir affiché la moitié du
résultat. Les deux appellent désormais `core.cli.configurer_stdout`.

### Tests

`tests/test_manga_bubbles_split.py` (31 tests). Ce qui est verrouillé : `composantes` est une
partition exacte, triée par aire, en 4-connexité ; un bi-lobé est scindé et l'union des lobes
vaut le masque d'origine ; **une bulle unique, un rectangle, une région trop petite et un lobe
trop maigre ne sont jamais scindés** ; un éclat détaché ne fait pas rejeter une bonne scission ;
la scission est déterministe ; l'ordre des autres régions est préservé (l'alignement par
position en dépend) ; `kind != "bulle"` et `actif: false` sont respectés ; le drapeau `scindee`
survit au cache ; la migration v2→v3 invalide les textes d'une page scindée et **ne touche pas**
à une page saine, et elle est idempotente. Suite complète : **822 tests**.

## [0.15.0] - 2026-08-14

**Lot 4.1 — glossaire de volume : la terminologie passe sur toutes les planches avant la
première traduction.** MINEUR : rien ne casse, aucun cache n'est invalidé, aucun flag ne
change. Terminologue désactivé (le défaut), le rendu du tome de référence est **identique à
l'octet** — vérifié sur les planches 1, 64, 136 et 142 après un `--from rendu` complet, avec
le glossaire de l'œuvre intact. Le light novel n'est pas touché (aucune ligne de `core/` ni de
`pipeline/`).

### Le défaut

`process_volume` enchaînait les six étapes **planche par planche**. Le relevé terminologique de
la planche 42 n'existait donc qu'après la traduction de la planche 41 :

- la planche 1 était traduite avec un glossaire **vide** ;
- `optimize_glossary_file` (dédoublonnage par le glossariste) tournait **après** la boucle : il
  nettoyait un glossaire dont les 150 planches s'étaient déjà servies, donc ne profitait qu'au
  run **suivant** ;
- `gloss_text` était re-sérialisé après chaque planche qui ajoutait quoi que ce soit — deux
  planches n'étaient jamais traduites avec la même terminologie.

C'est la cause du défaut mesuré au lot 3 (un même kanji rendu Mitsukage, Mikage puis Miyage),
que le forçage ne fait que rattraper après coup.

### Le traitement se fait désormais en deux balayages

```
A. par planche : détection → nettoyage → OCR        (aucun appel LLM)
B. tout le volume : relevé terminologique → dédoublonnage du glossaire
C. par planche : traduction → forçage → lettrage → rendu
```

- `manga/orchestrator_manga.py` — deux boucles séparées par `_passe_terminologie`, nouvelle
  fonction de module (donc testable seule). `checkpoints.STAGES`, le graphe `_DEPENDANTS` et
  `CACHE_NON_BLOQUANT` sont **inchangés** : l'étape `terminologie` garde son cache par planche
  et `--from terminologie` garde son sens.
- L'arrêt propre (`--stop`) peut maintenant tomber dans **trois** fenêtres. Le corps de sortie
  — assembler ce qui existe, fermer les sockets, rendre la main — est extrait en une fonction
  locale, seule façon de garantir qu'aucune des trois ne l'oublie.
- Les modèles de vision sont relâchés à la fin du balayage A, avant que le LLM ne soit
  sollicité. En une seule passe, détection et traduction s'entrelaçaient jusqu'à la dernière
  planche.
- `gloss_text` n'est plus rendu qu'**une fois** pour tout le tome (c'est la définition d'un
  glossaire fixe), et l'index est reconstruit après le dédoublonnage — `build_index` n'est
  valide que tant que le glossaire est *muté*, pas quand il est *remplacé*.

### Deux défauts trouvés en chemin

**Un tome OCRisé avant l'activation du terminologue n'était jamais relevé.** Le droit de
relever était adossé à l'étape `terminologie`, dont le cache est délibérément *non bloquant*
(son absence ne périme rien) : elle ne figurait donc dans les étapes à refaire que si on l'avait
explicitement demandée. Un tome dont la détection et l'OCR étaient déjà en cache se faisait
traduire avec un glossaire vide, sans un mot. Le droit d'appel est désormais adossé à la
**traduction** : une planche qu'on traduit coûte déjà un appel LLM, une planche qu'on ne
traduit pas n'en coûtera aucun. C'est aussi ce qui rend `--page 7` peu cher — les relevés des
autres planches sont relus depuis le cache, ce qui reconstitue le glossaire du volume
gratuitement.

**`merge_notes` signale une fusion fantôme.** Re-fusionner des notes déjà intégrées renvoie
`{"fusions": 1}` alors que rien ne change. S'y fier réécrivait `glossaire.yaml` à chaque
planche — 150 écritures par run — et, plus grave, rappelait le glossariste (un appel LLM sur
tout le glossaire) à chaque relance d'un tome déjà relevé. Le changement se mesure désormais
sur une **empreinte** du glossaire rendu (`to_sectioned`, qui couvre tous les champs de
`FIELD_ORDER`, 0,03 ms).

### Conséquence pratique

Sur un tome neuf, aucune planche traduite n'apparaît avant que les 150 ne soient détectées et
OCRisées. Le coût total est le même ; c'est l'ordre qui change.

### Tests

`tests/test_manga_prepasse.py` (10 tests, tous sans LLM — le traducteur, le terminologue et le
glossariste sont des doubles qui journalisent). Ce qui est verrouillé : un terme relevé sur la
planche 3 est présent dans le prompt de la planche 1 ; aucun relevé n'a lieu après la première
traduction ; les trois planches reçoivent la **même** sérialisation de glossaire ; le
dédoublonnage précède la première traduction et n'a lieu qu'une fois ; relancer un tome déjà
relevé ne rappelle ni le terminologue ni le glossariste et ne réécrit pas le fichier ;
`--page 1` ne consomme qu'un relevé mais voit tout le volume ; `--from rendu` ne déclenche
aucune passe ; un arrêt pendant la passe conserve l'acquis. Suite complète : **791 tests**.

`tests/test_manga_runtime.py` — le trafic du terminologue y était **simulé** à la main, faute
d'être réellement produit par l'orchestrateur (le trou décrit plus haut). Il est maintenant
réel, et le test l'exige.

## [0.14.0] - 2026-08-13

**Lot 3 — cohérence terminologique manga.** MINEUR : une nouvelle étape, un nouvel agent
optionnel, un outil de mesure ; tous les défauts sont iso-comportement. Le light novel n'est
pas touché (tome en `--dry-run` identique). **Fin du chantier.**

Mesuré sur *manga A* Vol.1, avant/après un seul `--from rendu` :
**39 orthographes bannies → 0**, en 5 min et **sans un seul appel LLM**.

| Source | Rendus par le modèle | Après |
|---|---|---|
| `カタフラクト` | Kataphrakt · Katafrakt · Kataphrakto · Cataphracte | **Kataphrakt** |
| `リベルティナ` | Libertina (13) · Ribitina · Libidina | **Libertina** (15) |
| `クルーテオ` | Kuran (2) · Cluteo · Kruuteo | **Cruhteo** (4) |
| `アセイラム` | Aselam (4) · Asylum | **Asseylum** (5) |
| `三影` (kanji) | Mitsukage (12) · Mikage · Miyage | **Mitsukage** (13) |
| `弥月` (kanji) | Yuzuki (6) · Miyuki (4) · Yozuki | **Yuzuki** (11) |

Les deux dernières lignes sont les plus parlantes : ce sont des **kanji**, strictement
identiques d'une bulle à l'autre. Aucune ambiguïté de lecture OCR ne peut l'expliquer — c'est
le modèle qui hésite, planche par planche, faute de mémoire de ce qu'il a écrit vingt planches
plus tôt. Un lecteur ne peut pas deviner que « Mikage » et « Mitsukage » sont la même
personne : une bulle est trop courte pour porter ce contexte.

### Ajouté

- **Forçage du glossaire sur les bulles** (`manga/terminology.py`, via
  `core.glossary_force.enforce_force` extrait au lot 2.5) : toute forme listée en
  `variantes`/`interdits` d'une entrée `force: true` est remplacée par la forme canonique,
  avec les garde-fous français d'élision et d'accord — un remplacement qui introduirait une
  faute d'accord est **refusé et signalé**, jamais appliqué. Bulle par bulle et non sur la
  page concaténée : la fin d'une bulle n'est pas le contexte grammatical du début de la
  suivante.
- **Étape `terminologie`**, entre `ocr` et `traduction` : le terminologue relève les noms
  propres depuis le **japonais OCR** (et, sur un tome déjà traduit, depuis le français produit
  — de quoi lister les variantes en `interdits`) et enrichit `sources/<Projet>/glossaire.yaml`,
  planche par planche, en fusion incrémentale. Le `glossariste` dédoublonne en fin de tome.
  Les deux agents sont ceux du light novel, réutilisés **tels quels** (ils sont agnostiques du
  média), et écrivent dans le **même fichier** — c'est ce qui garde les noms cohérents entre un
  roman et son manga. Optionnels et désactivés par défaut. Chaque relevé est mis en cache
  (`.checkpoints/page_XXXX/terminologie.txt`).
- `--from terminologie`, et `tools/compter_variantes.py` — combien de formes bannies
  subsistent, lu depuis `qa.json` (ce que le lecteur voit) ou `--brut` (la sortie du modèle).
  Sans glossaire, l'outil bascule en mode exploratoire et propose les familles candidates :
  c'est ce mode qui a établi la liste initiale.
- `sources/manga A/glossaire.yaml`, 17 entrées. Les formes officielles de la
  franchise là où elles existent (manga A, Kataphrakt, Asseylum, Cruhteo, Vers, Sleipnir,
  Areion, Hypergate, Heaven's Fall), la forme dominante ailleurs. Les lectures **non
  vérifiées** sont dites comme telles dans leur `description` (青坂 se lit Aozaka ou Aosaka
  selon les familles) : corriger `nom` et relancer `--from rendu` suffit à réécrire le tome.
- Le rapport compte les remplacements, liste les refus, et **distingue « 0 remplacement parce
  que tout était canonique » de « aucune entrée `force: true` »** — le second veut dire que la
  cohérence n'est pas garantie du tout.

### Corrigé

- **Les glossaires d'œuvre n'étaient pas versionnés.** `sources/*` les emportait avec les
  scans, alors que ce n'est pas du scan mais du travail écrit à la main : 136 Ko et 441 entrées
  sur sept œuvres (formes canoniques, variantes bannies, genres, et le raisonnement derrière
  chaque choix) qu'un clone frais aurait perdus. Quatre lignes de `.gitignore` les
  ré-incluent — et il en faut quatre, parce que git refuse de ré-inclure un fichier sous un
  répertoire exclu : on ré-inclut les dossiers d'œuvre, on re-exclut leur contenu, on
  ré-inclut le seul glossaire, puis on rétablit `sources/Demo LN/`. Vérifié dans les deux
  sens : les sept glossaires entrent, aucun scan ne suit.
- **`tools/compter_variantes.py` mesurait faux dans sa première version** : ses frontières de
  mot excluaient l'apostrophe, si bien que `l'Areyon` n'était pas compté. Le total d'avant en
  était sous-estimé (38 au lieu de 39) et — bien plus grave — une forme bannie survivant après
  une élision serait passée pour éliminée. Il utilise désormais `\b`, exactement comme le
  mécanisme qu'il mesure.
- `first_missing_stage` **supprimée** : elle rendait un *indice* dans `STAGES` (« 3 » =
  traduction), donc insérer une étape en aurait décalé le sens sans qu'aucun appel ne casse.
  Elle n'avait plus de call site en production depuis le lot 1.

### Le piège évité, et il aurait coûté cher

Insérer une étape dans le graphe fait apparaître un cache absent sur **toutes** les planches
déjà traitées : `terminologie.txt` n'existe nulle part sur un tome traduit avant ce lot. Si son
absence périmait la traduction — comme le fait celle de l'OCR — un simple `--from nettoyage`
aurait déclenché la **retraduction des 150 planches**, appels LLM compris, et activer l'agent
aurait fait pire encore.

L'étape écrit dans le glossaire de l'**œuvre**, pas dans le cache de la page ; son fichier ne
sert qu'à ne pas repayer l'appel. `CACHE_NON_BLOQUANT` acte cette différence de nature, et un
test la verrouille dans les deux sens (absence → rien de périmé ; `--from terminologie` →
traduction bien réinvalidée).

### Choix de conception à connaître

Le forçage s'applique à l'**usage**, pas à l'écriture du cache : `traduction.json` garde la
sortie brute du modèle. C'est l'inverse du light novel, et pour une raison précise — le LN doit
stocker le texte forcé parce que son correcteur travaille ensuite dessus, tandis que la brique
manga n'a aucun agent en aval (l'étape suivante est un lettrage déterministe). Le bénéfice est
direct : corriger une orthographe dans le glossaire et relancer `--from rendu` réécrit les 150
planches sans LLM. Stocker le texte forcé imposerait de retraduire le tome à chaque correction.

## [0.13.0] - 2026-08-13

**Lot 2.6 — `core/report.py`, `core/cli.py`, et le sens des dépendances remis d'aplomb.**
MINEUR : `run_manga.py` gagne trois flags, et une ligne de `RAPPORT.md` change de
formulation côté light novel. **Fin du lot 2.**

### Ajouté

- **`run_manga.py --keep-awake` / `--shutdown` / `--shutdown-delay`**, absents jusqu'ici et
  plus utiles encore côté manga : un tome de 150 planches avec le raisonnement activé dépasse
  les deux heures, donc se lance la nuit. Mêmes flags, même code, même ordre subtil
  (l'anti-veille n'est levé qu'APRÈS le délai d'extinction, sinon Windows peut endormir le PC
  pendant l'attente et figer le `shutdown /s`). Le modèle est aussi préchargé et déchargé,
  comme côté light novel.
- `core/report.py` — en-tête de run (version, heure de fin, durée), bloc de statistiques LLM,
  troncature des longues listes, écriture du fichier. Le *contenu* des deux rapports n'a
  presque rien en commun ; leur squelette, si — et il avait déjà divergé, avec deux
  formulations différentes pour « pas de statistique LLM ». Un test vérifie qu'aucune des deux
  briques ne reformate la ligne « Appels LLM » à la main.
- `core/cli.py` — configuration UTF-8 de stdout, chargement de config, rendu de `--list`,
  `perf.log`, flags de veille, anti-veille/préchargement/déchargement/extinction, et les
  sections de doctor réellement communes (Ollama, dépendances Python, ligne de conclusion).
- `tests/test_core_report.py` (14), `tests/test_core_cli.py` (17).

### Corrigé

- **`app.py` n'importe plus `run.py`.** Il y prenait `_finalize_power`, `_models_in_config`,
  `_unload_models` et `_run_doctor` : une inversion de couche, la TUI dépendant d'une CLI
  concurrente — on ne pouvait pas toucher à `run.py` sans risquer de casser `app.py`. Le cycle
  de vie de l'alimentation vit maintenant dans `core/cli.py` ; le diagnostic light novel dans
  **`pipeline/doctor.py`**, et **non** dans le socle : sections de `config.yaml`, Pandoc,
  moteur PDF, `reference.docx`, `epub.css` — tout y est propre à la brique, et le mettre dans
  `core/` y aurait fait entrer la connaissance d'une brique, exactement ce que le lot 2
  défait. Un test le vérifie sur l'AST (les docstrings du socle *citent* `reference_docx`
  comme contre-exemple, un `not in texte` se déclencherait dessus).
- **`--from rendu` ne précharge plus le modèle de traduction.** Le préchargement manga, ajouté
  quelques lignes plus haut dans ce même lot, aurait fait monter un modèle de 27 B en VRAM
  pour une commande qui n'appelle jamais le LLM — et le déchargement final aurait évincé celui
  que l'utilisateur avait peut-être chargé pour autre chose. C'est la commande de vérification
  du lot 1, et le même raisonnement que le chargement paresseux du détecteur ONNX. La garde
  s'appuie sur le graphe d'étapes (`downstream`), pas sur une comparaison de noms.
- Une reprise light novel entièrement en cache n'annonce plus « (dry-run — aucune statistique
  LLM) » ou un décompte à zéro selon le cas, mais la formulation unique « (dry-run ou aucun
  appel — pas de statistique LLM) ». Seul changement de sortie du lot, vérifié sur un tome en
  `--dry-run` : c'est la seule ligne qui bouge.

### Écarts assumés par rapport au plan

- Le plan prévoyait d'extraire aussi les flags `--version`/`--config`/`--verbose`/`--dry-run`
  vers `core/cli.py`. Ils ne sont communs qu'en apparence : `--verbose` ne mesure pas la même
  chose des deux côtés (temps/tokens par bloc contre par étage de planche) et `--dry-run` non
  plus (aucun appel LLM contre détection et OCR **réels**, seule la traduction sautée). Les
  factoriser derrière des paramètres d'aide aurait donné un helper plus long que les six
  `add_argument` remplacés, en bousculant l'ordre du `--help` d'une des deux CLI. Seuls les
  trois flags de veille — nom, sémantique **et** texte d'aide identiques — sont partagés.
- `core/glossary_force.py`, listé dans l'arborescence cible du plan mais absent de son tableau
  d'étapes, a été livré au lot 2.5. Le lot 3 en dépend.

## [0.12.1] - 2026-08-13

**Lot 2.5 — `core/quality.py` (moteur de garde-fous) et `core/glossary_force.py`.**
CORRECTIF : aucun changement de comportement. Le light novel garde ses huit contrôles à
l'identique — vérifié par ses onze tests de moteur et par un tome en `--dry-run` **identique
à l'octet près**, ligne de version comprise cette fois.

### Modifié

- `core/quality.py` — `out_cap`, `premier_motif`, `try_with_temp_retry`. Le moteur est
  agnostique des **contrôles**, pas « de l'unité de travail » : la nuance est ce qui rend
  l'extraction possible. Sur les huit motifs du light novel, trois seulement sont universels
  (`vide`, `emballement`, `repetition`), un l'est à moitié (`perte_mots`) et trois sont
  ancrés dans des artefacts light novel — `troncature_image` lit `<!-- IMG: -->`,
  `titre_perdu` lit les titres ATX, `styleguide_fuite` lit un guide de style que le manga
  n'injecte jamais. Chaque brique fournit donc son **registre ordonné de `(nom, prédicat)`**
  et son type de contexte ; le socle ne voit qu'un `diagnostiquer(sortie) -> nom | None`, et
  un test vérifie qu'il n'inspecte jamais le contexte.
- Les huit contrôles light novel, jusque-là une cascade de `if` dans une fermeture, sont
  devenus huit prédicats nommés et un registre. L'ordre est conservé exactement, et il
  compte : `repetition` est testé **avant** `emballement`, ce qui étiquette « repetition » un
  bloc ayant bouclé jusqu'à saturer son plafond — donc le fait redécouper (cf.
  `_RESPLIT_REASONS`, qui s'appuie sur cet ordre).
- Trois paramètres, un par différence réelle entre les briques : `cle_ok`
  (« blocs_ok » / « pages_ok »), `motifs_plus_chaud`, et `prefere` — « meilleure sortie »
  n'ayant pas le même sens (mots de récit récupérables pour un bloc, répliques numérotées
  pour une planche). Côté light novel la comparaison n'a lieu qu'à motif **égal** : comparer
  des longueurs entre deux pathologies distinctes n'a pas de sens. C'est la branche qu'un
  partage négligent aurait perdue en silence — `tests/test_core_quality.py` (16 tests) et un
  nouveau test light novel la couvrent, vérifié en retirant la garde : il tombe.
- `core/glossary_force.py` — `enforce_force` et `match_case`, déplacés **sans changer une
  ligne**. Rien là-dedans n'est propre au light novel : c'est du texte brut et un glossaire,
  avec la gestion française de l'élision et de l'accord. Le lot 3 les appliquera aux chaînes
  de bulles, où le besoin est plus fort encore — une bulle est trop courte pour qu'un lecteur
  devine le terme canonique d'après le contexte.
- `pipeline/orchestrator.py` tombe de 1733 à 1567 lignes et ré-expose les symboles déplacés
  sous leurs anciens noms privés (`_out_cap`, `_enforce_force`, `_match_case`).
  `manga/quality_manga.py` garde sa signature publique : l'orchestrateur manga et ses 27
  tests ne bougent pas.

### Corrigé

- `test_chapitre_n_only_recomputes_target` échouait **au hasard**, environ une fois sur 60
  exécutions de la suite : il comparait deux rendus caractère par caractère, en-tête
  d'empreinte compris — or celui-ci porte la MINUTE, et le test lance deux
  `process_volume` d'affilée. Défaut introduit au lot 0 avec l'en-tête lui-même, resté
  invisible six versions. L'en-tête est désormais retiré avant comparaison : ce n'est pas ce
  que le test vérifie.

## [0.12.0] - 2026-08-13

**Lot 2.4 — `core/runtime.py` : cycle de vie des clients LLM, branché sur le manga.**
MINEUR : la brique manga gagne trois garde-fous qu'elle n'avait pas. Les quatre fonctions
sont déplacées **sans changer une ligne** ; c'est leur branchement qui est nouveau.

### Ajouté

- `core/runtime.py` — `all_llm_clients`, `close_llm_clients`, `wire_reporter`,
  `aggregate_llm_stats`, extraites telles quelles de `pipeline/orchestrator.py`. Elles ne
  connaissent rien de l'unité de travail : elles ne voient qu'un client par défaut et un
  dictionnaire d'agents. C'est exactement la frontière d'extraction du lot 2, et c'est
  pourquoi elles sortaient en premier. `pipeline/orchestrator.py` les ré-expose sous leurs
  anciens noms privés — 25 call sites et `tests/test_orchestrator.py` n'ont pas à bouger
  pour un déplacement.
- **Les incidents des clients LLM manga atteignent `perf.log`.** Budget « thinking » épuisé,
  nouvelle tentative, réponse inexploitable : tout cela partait sur stdout via un `print()`
  brut. Après un run de nuit sur 150 planches, plus aucune trace de quelle page avait dérapé
  ni pourquoi — et en mode TUI ces messages corrompaient la barre de progression Live. Le LN
  avait ce branchement depuis longtemps, la brique manga non.
- **Les sockets vers Ollama sont fermées**, à la fin du run *et* à l'arrêt propre. Une par
  run restait pendante. `--stop` est le cas fréquent sur un tome long : c'est là qu'il ne
  faut surtout pas l'oublier.
- **Le rapport manga somme les compteurs de tous les clients**, plus seulement celui du
  traducteur. Ce n'est pas encore un bug observable — la brique n'a qu'un agent, qui fait
  tous les appels — mais ça le devient dès que `endpoint:` fonctionne (lot 2.2) et que le
  lot 3 branchera `terminologue`/`glossariste` : chacun sur son endpoint aura son propre
  client. C'est le défaut que le LN avait mesuré chez lui, 79 appels annoncés contre 183
  réellement tracés dans `perf.log`.
- `tests/test_manga_runtime.py` (6 tests, en run NON dry-run — en dry-run les clients valent
  `None` et il n'y a rien à brancher). Quatre d'entre eux ont été vérifiés en retirant
  temporairement les trois appels : les quatre tombent.

### Modifié

- Une reprise entièrement en cache n'affiche plus « Appels LLM : 0 · ~0 tok/s », qui se lit
  comme une mesure, mais la ligne « aucun appel — pas de statistique LLM » qui existait déjà
  pour le dry-run. Seul changement de sortie du lot.

## [0.11.1] - 2026-08-13

**Lot 2.3 — `core/config.py`, héritage par fusion profonde.** CORRECTIF : les valeurs
résolues sont identiques sur le chemin nominal (`config.yaml` livré), mais deux pièges
silencieux disparaissent.

### Corrigé

- **`manga.llm` ne remplace plus la racine en bloc.** `mcfg.get("llm") or config["llm"]`
  était du tout-ou-rien : décommenter le bloc `manga.llm` de `config.yaml` pour n'y régler
  qu'un `thinking_budget` faisait perdre `llm.endpoints`, `extra_directive` et tout ce qui
  n'y était pas recopié — avec un run qui démarre normalement, et un
  `endpoint: "reflexion"` par ailleurs correct qui échoue en `SystemExit`. Le fichier avait
  fini par *documenter* le piège (« ⚠ TOUT-OU-RIEN : il faut donc y recopier
  base_url/api_key/timeout ») plutôt que de le corriger. Vérifié en décommentant réellement
  le bloc : `base_url` et `endpoints` sont hérités, `max_retries` et `thinking_budget`
  propres à la brique s'appliquent.
- **`manga.chemins` ne duplique plus `sources` et `build`.** Deux copies verbatim de la
  racine, avec le commentaire « même racine que le LN » : changer la seule racine faisait
  écrire la brique manga à l'ancien endroit, sans un mot. Le bloc est désormais vide et
  hérité — et la brique gagne au passage `glossaire_fichier`, que
  `orchestrator_manga.py` allait chercher dans `config["chemins"]` alors qu'il lisait
  `sources`/`build` dans `mcfg["chemins"]` : deux origines pour un même bloc, à trois
  lignes d'intervalle. `run_manga.py` résout ses chemins en un seul endroit (`_chemins` /
  `_build_dir`), les trois call sites de `build/<projet>/<tome>/manga` ayant l'obligation
  de viser le même dossier — sinon `--stop` demande l'arrêt d'un run qui écoute ailleurs.

### Ajouté

- `core/config.py` : `deep_merge`, `section(config, brique, cle)`, `origine(…)`. Deux règles
  portant toutes deux sur `None` et allant en sens **opposés**, chacune testée : un
  **scalaire** nul de la surcouche gagne — `think: null` (« défaut du modèle ») est distinct
  de `think: false` (« pas de raisonnement »), et sans cela une brique ne pourrait pas
  revenir au défaut du modèle quand la racine impose `false` ; un **sous-arbre** nul est
  hérité — `manga:` `llm:` écrit puis laissé vide est un accident YAML, jamais une demande
  d'effacement. Les listes remplacent et ne se concatènent pas : une liste de `config.yaml`
  est une énumération complète (`formats`, `providers`), concaténer rendrait impossible d'en
  retirer un élément.
- L'héritage est **opt-in bloc par bloc**, et c'est nécessaire : la racine et le manga ont
  tous deux un bloc `rendu:` qui ne parle pas de la même chose (`reference_docx`,
  `epub_css`, `pdf_engine` d'un côté ; sens de lecture et qualité JPEG de l'autre). Les
  fusionner ferait entrer dans le rendu manga des clés qui n'y ont aucun sens. Un test
  vérifie que personne n'a « simplifié » en fusionnant la section entière.
- Le diagnostic d'endpoint mal indenté nomme désormais **deux** blocs : celui où la clé se
  trouve et celui où il faut l'ajouter. Depuis la fusion ce n'est plus forcément le même, et
  pointer le mauvais fait perdre exactement le temps que ce message économise.
- `tests/test_config.py` (20 tests). Les fixtures manga règlent maintenant la racine et non
  `manga.chemins` : elles sont devenues le test de bout en bout de l'héritage.

## [0.11.0] - 2026-08-13

**Lot 2.2 — `build_agents` unique pour les deux briques.** MINEUR : la brique manga gagne
des capacités, rien ne casse. Le Markdown d'un tome LN en `--dry-run` reste identique hors
la ligne de version elle-même.

### Ajouté

- **`endpoint:` fonctionne enfin côté manga.** C'était le défaut le plus vicieux de la
  brique : écrire `manga_traducteur: {model: …, endpoint: "reflexion"}` ne produisait
  **aucun effet et aucun message** — l'agent tournait sur le serveur par défaut, sans
  raisonnement. `config.yaml` en était réduit à *documenter* le piège (« ⚠ `endpoint:`
  n'est PAS lu … l'idiome serait SILENCIEUSEMENT ignoré ») au lieu de le corriger. Cause
  directe : `build_manga_agents` n'avait **aucun test**, alors que le LN en avait huit sur
  cette exacte mécanique.
- Le manga hérite aussi des **diagnostics de config mal indentée** (le `endpoints: {}` vide
  qui ferme le dictionnaire avant la définition écrite en dessous), du **partage de client
  par endpoint** — un roster de N agents ouvrait N pools de sockets vers le même Ollama —
  et d'`extra_directive`, qui est par construction une directive *globale* (« ajouté à la
  fin de chaque message utilisateur ») et que seul le LN appliquait.
- Symétriquement, le LN gagne la forme **en ligne** `{model: …, think: true}` de la brique
  manga : plus besoin de déclarer un endpoint pour le seul réglage `think`. Écrite en plus
  d'un `endpoint:`, elle l'**affine** (le plus spécifique gagne).
- Une température manquante n'est plus un `KeyError` nu côté LN mais un message qui dit
  quoi ajouter et où. Le LN reste **strict** ; le manga garde son repli à 0,3.
- `tests/test_manga_agents.py` (15 tests) et cinq tests LN de plus. Dont un qui fixe le
  comportement **tout-ou-rien** de `manga.llm` tel qu'il est *aujourd'hui* : c'est le lot
  2.3 qui le renversera, et la bascule doit se voir dans son diff plutôt que d'être noyée
  dans ce refactor.

### Modifié

- `core.agents.build_agents(config, llm=None, dry_run=False, *, section=, names=,
  agent_cls=, temperature_defaut=)` remplace les deux constructions parallèles. Les seules
  différences réelles entre elles étaient : quelle section porte les réglages LLM, d'où
  vient la liste des agents, et quelle classe instancier. Tout le reste était écrit deux
  fois — une seule des deux versions étant complète.
- `names=None` vaut `NOMS_LN` à la racine et les clés de `modeles` dans une section : le LN
  a besoin d'un roster **fixe** (l'orchestrateur teste `agents["correcteur"] is None` pour
  sauter une étape désactivée, donc la clé doit exister même absente de la config), le
  manga d'un roster **ouvert**. Ce n'est pas une commodité, c'est une contrainte opposée.
- `agent_cls` est passé par l'appelant et non résolu dans le socle : `core/` importerait
  sinon `manga/`, en rétablissant la dépendance que le lot 2.1 vient de défaire.
- `manga/agents_manga.py` tombe de 64 à ~50 lignes, dont plus rien que `MangaAgent` et un
  appel de trois lignes.

## [0.10.1] - 2026-08-13

**Lot 2.1 — le socle `core/` prend ses neuf premiers modules.** CORRECTIF : refactor
**prouvablement neutre**, aucun changement d'interface ni de sortie. Vérifié par un tome LN
en `--dry-run` avant/après — le Markdown assemblé est identique **à l'octet près**, hors la
minute d'horodatage.

### Modifié

- `agents`, `control`, `glossary`, `glossary_build`, `glossary_import`, `llm`, `power`,
  `reporter` et `tokens` passent de `pipeline/` à `core/`. Aucun ne contenait quoi que ce
  soit de propre au light novel — `manga/` en importait déjà six, ce qui faisait dépendre la
  brique manga du paquet `pipeline`. Les neuf déplacements se relisent avec
  `git diff -C --find-copies-harder`, qui les affiche en `{pipeline => core}/x.py | 0` :
  zéro ligne modifiée. Et **non** `--find-renames` comme prescrit — la détection de renommage
  exige que le chemin source ait disparu, or l'alias l'occupe encore ; il faut donc la
  détection de *copies*.
- Neuf alias `pipeline/<nom>.py` de trois lignes conservent les imports existants, par
  **auto-remplacement dans `sys.modules`** et non par `from core.<nom> import *`. La forme
  étoilée créerait un *objet module distinct* dont les globals ne sont qu'un instantané :
  patcher `pipeline.agents.LLM` ne toucherait plus ce que `core.agents.build_agents` résout,
  et les tests passeraient contre la vraie classe — donc bloqueraient sur une socket au lieu
  d'échouer clairement. `tests/test_core_alias.py` verrouille l'**identité d'objet**
  (`pipeline.agents is core.agents`), les deux voies d'accès (`sys.modules` et attribut du
  paquet parent), le fait qu'un patch par l'ancien chemin atteigne bien le code appelé, et
  la forme du shim elle-même — contrôlée sur l'AST, parce que les docstrings *citent*
  `import *` comme contre-exemple et qu'un `not in texte` se déclencherait dessus. Les
  quatre garde-fous ont été vérifiés en remplaçant temporairement un shim par la forme
  fautive : les quatre tombent.
- Le sens de la dépendance est désormais testé : `core/` n'importe ni `pipeline` ni `manga`.
  Sans ce test, un import de brique dans le socle *fonctionnerait* — via les alias —
  recréant en silence le cycle qu'on vient de défaire.

## [0.10.0] - 2026-08-13

**Lot 1 — remise à niveau du rendu manga.** MINEUR : de nouvelles clés de config, un nouveau
flag (`--assembler`), un `RAPPORT.md` et des garde-fous de traduction ; tous les défauts sont
optionnels et à défaut iso-comportement. Le format de `regions.json` passe à v2, mais la
migration est **automatique et sans recalcul** — donc pas de MAJEUR.

Vérifié de bout en bout sur *manga A* Vol.1 (150 planches, 797 bulles) :

| Critère | Avant | Après |
|---|---|---|
| Intérieurs de bulle sombres | 308 / 797 (117 pages) | **1** |
| Pixels de texte hors masque | non mesuré | **0** |
| Pages au-dessus du ratio de taille 1,25× | — | **0 / 124** |
| Lignes de lettrage | 3364 | **2671** (−21 %) |
| `--from nettoyage` sur le tome | ~38 min + appels LLM | **3 min**, 0 LLM |
| CBZ après interruption | jamais produit | **produit** |

### Ajouté

- **Ordre de lecture par coupe X-Y récursive** (`manga/ocr.py`) : plus grande gouttière
  horizontale contre verticale, en écart normalisé ; horizontale → haut puis bas, verticale →
  **droite puis gauche**. *Panel-aware sans jamais détecter les cases* — les gouttières entre
  cases sont les gouttières entre groupes de bulles. Remplace une agrégation par chevauchement
  vertical calculée sur toute la largeur de la page, qui entrelaçait deux cases côte à côte
  (page 20 : cinq bulles de deux cases dans la même « bande », donc lues en zigzag).
- **`masked_crop`** : la bulle est isolée sur une toile de sa **couleur mesurée** avant l'OCR.
  `image.crop(bbox)` laissait entrer le texte de la bulle voisine, que `manga-ocr` lisait
  aussi. La couleur mesurée et non du blanc : sur une bulle inversée, du blanc autour d'un
  texte clair détruirait le contraste.
- **`ComicInfo.xml`** en première entrée du CBZ, avec `Manga=YesAndRightToLeft` (clé lue par
  Komga, Kavita, YACReader, Mihon, ComicRack). Valeurs échappées : « Tom & Jerry » produisait
  un XML invalide, que certains lecteurs rejettent en bloc — l'archive s'ouvrait alors sans
  aucune métadonnée.
- **`run_manga.py --assembler`** : n'exécute que l'assemblage depuis `pages_out/`.
- **Garde-fous de traduction** (`manga/quality_manga.py`) : plafond de sortie `bubbles_cap`,
  registre ordonné de six motifs d'échec, retry à température corrigée (plus froid, sauf sur
  boucle où on la relève). Le moteur prend un callable `call(temperature) -> str` et non un
  `Agent` : testable sans LLM, et prêt pour l'extraction vers `core/quality.py` au lot 2.
- **`RAPPORT.md` manga** (`manga/report_manga.py`) + un `qa.json` **par page**. Les pages
  réutilisées du cache ne produisent aucune statistique fraîche : le rapport est donc bâti en
  relisant *toutes* les pages, sinon une reprise donnerait un rapport quasi vide, donc
  mensonger. Reproduit les chiffres du diagnostic à l'identique — 19 pages sans bulle, 3
  traductions vides, 28 détections sous 0,60.
- **Contexte de traduction** : dimensions de chaque bulle avec un budget de caractères (le
  prompt demandait d'être bref sans dire *à quel point* — 54 traductions dépassaient 90
  caractères) et répliques de la planche précédente, pour la continuité du dialogue.
- Nouvelles clés optionnelles `manga.ocr.*`, `manga.rendu.*` (sens de lecture, dpi, qualité,
  largeur max) et `manga.rapport.*`.

### Ajouté (suite)

- **Polices de lettrage livrées** : famille **Comic Neue** (Regular/Bold/Italic/BoldItalic)
  sous **SIL OFL 1.1**, avec `OFL.txt` et `templates/fonts/README.md` (origine, licence,
  chaîne de repli, substitution). `templates/fonts/` n'existait pas et la chaîne tombait
  **systématiquement sur Arial** — une police de traitement de texte, qui trahit une planche
  au premier coup d'œil.
- **Repli de police par bulle** (`font_pour_texte`) : Comic Neue est une police latine et n'a
  ni `♪` ni `♥` ni `→`, que le traducteur produit pourtant (« Moi, je préfère les filles ♪ »)
  — la planche sortait avec un carré « tofu ». La première police de la chaîne qui couvre
  réellement le texte est choisie pour cette bulle-là ; si aucune ne le couvre, les
  caractères sont **signalés**. Détection fiable : `font.getmask(c).getbbox() is None` ne
  détecte **pas** un glyphe absent (Pillow substitue le `.notdef`, de boîte non vide), on
  compare donc au rendu d'un caractère à coup sûr absent.
- Nouvelles clés optionnelles `manga.typeset.*` (tailles, interlignes, marge, majuscules,
  césure, contour, harmonisation, débordement).

- `manga/geometry.py` : morphologie en **numpy pur**, aucune dépendance ajoutée. Érosion et
  dilatation par élément structurant carré séparable, **identiques bit-à-bit à
  `PIL.ImageFilter.MinFilter`** (vérifié pour k = 1 à 8) et à coût **indépendant du rayon**
  grâce aux sommes cumulées — 1,3 ms contre 21,6 ms à k=8 sur un masque 227×360. Ajouter
  opencv (~60 Mo, conflits de DLL avec `onnxruntime-directml`) aurait été un gain nul.
- `width_profile()` renvoie, par ligne, la plage **contiguë contenant le centroïde** et non
  `premier..dernier` : c'est ce qui exclut la **queue** de la bulle (mesuré page 20 : 120 px
  utiles au lieu de 155 annoncés) et gère les masques **bi-lobés**.
- `manga/clean.py` expose `BubbleStyle` / `analyze_bubble` / `analyze_regions` : tout ce que
  le nettoyage a mesuré (couleur de fond, polarité, uniformité, intérieur, centroïde) est
  désormais transmis au lettrage, qui ne peut pas le redécouvrir après coup.
- Nouvelles clés optionnelles `manga.nettoyage.*` (`marge_bord`, `mode`,
  `seuil_uniformite`, `seuil_abandon`, `seuil_texte`, `dilatation_texte`, couleurs de
  texte).
- `tests/test_manga_orchestrator_cache.py` : l'orchestrateur manga n'avait **aucune
  couverture** sur une machine sans le modèle ONNX (`test_manga_orchestrator.py` est sauté
  en entier). Les reprises en cache sont désormais testées, modèle absent compris.

### Corrigé

- **308 bulles sur 797, réparties sur 117 des 150 planches, étaient repeintes en gris ou en
  noir** au lieu de blanc. `detection.py` renvoie le masque de TOUTE la bulle, contour
  compris, mais `clean.py` était écrit comme si c'était un masque de TEXTE : il
  échantillonnait `~mask` dans la bbox, c'est-à-dire le **dessin autour** de la bulle
  (page 60 : (139,139,139), (118,118,118), (35,35,35), (112,112,112) pour des bulles
  blanches), et remplir tout le masque effaçait en outre le **trait de contour**, à cheval
  sur la frontière. Combiné au `fill=(0,0,0)` en dur du lettrage : texte noir sur fond noir.
  Correctif : éroder d'abord (`safe_erode`), mesurer et peindre l'intérieur seulement. Après
  réécriture, sur les mêmes 797 bulles : **1** intérieur sombre au lieu de 308, et le dessin
  hors masque reste bit-à-bit identique.
- La couleur de fond vient du **mode** d'un histogramme de luminance, jamais d'une médiane
  ni d'un percentile : sur la bulle sombre de `page_0044` un p90 renverrait 193, soit la
  couleur du **texte**. La polarité est **héritée du contraste mesuré**, pas déduite d'un
  seuil de luma — une bulle grise à luma 120 avec du texte noir garde du texte noir.
- Nouveau mode de nettoyage **`"aucun"`** (`seuil_abandon`, défaut 0,35), trouvé au contrôle
  visuel : sur `page_0044`, le détecteur avait pris un **gratte-ciel** aux fenêtres sombres
  pour une bulle (uniformité 0,131, fond mesuré à luma 4). En mode « texte », toute la
  structure claire du bâtiment devenait le masque de texte et était repeinte en noir — le
  dessin était détruit. En dessous du seuil, on ne peint plus rien. Le seuil tombe dans un
  creux net de la distribution (deux détections à 0,131 et 0,226, la suivante à 0,457), donc
  il isole exactement ces deux cas sur 797.
- **`--from nettoyage` et `--from rendu` étaient impossibles sans le modèle ONNX**, alors
  qu'ils n'en ont pas besoin (les régions viennent de `.checkpoints/`) : `BubbleDetector` —
  qui lève `SystemExit` si le `.onnx` manque — et `MangaOCR()` — qui charge un ViT+BERT —
  étaient construits inconditionnellement avant la boucle des pages. Chargement désormais
  paresseux.
- Les styles de bulle sont analysés sur l'image **d'origine** à chaque reprise, jamais sur la
  page nettoyée : sur une page déjà nettoyée la bulle est uniforme, la polarité devient
  indéductible, et un `--from rendu` relettrerait une bulle inversée en noir sur noir.
- **`--from` suit désormais le graphe de dépendances, plus l'ordre d'exécution.** Les étapes
  ne forment pas une chaîne : `ocr` lit l'image d'origine et les régions, jamais la page
  nettoyée. `nettoyage` et `ocr` sont donc des frères issus de `detection` seule
  (`detection ─┬─ nettoyage ─┐` / `└─ ocr ─ traduction ─┴─ rendu`). `--from nettoyage`
  réinvalidait l'OCR (5,6 s/page) et la traduction (9,7 s/page, appels LLM compris) : ~38
  minutes sur un tome de 150 planches pour un résultat identique au bit près. Mesuré après
  correctif : **3 min 16 s pour les 150 planches, sans aucun appel LLM ni modèle chargé**.
  `checkpoints.stage_cache_present()` remplace au passage `first_missing_stage` là où il
  fallait connaître l'état de chaque étape indépendamment.
- Les bulles abandonnées sont signalées par `reporter.warn` (donc aussi dans `perf.log`),
  page et numéro de bulle à l'appui — un abandon est un incident, pas un silence.
- **Le CBZ n'était jamais produit après une interruption.** `_render_outputs` n'était atteint
  qu'**après** la boucle des pages, et tout `return False` sur `STOP`/Ctrl+C sortait avant
  l'assemblage — même quand les 150 pages étaient déjà sur disque. Défaut de structure, pas de
  `build_cbz`. `assemble_outputs` est désormais appelée aussi à l'arrêt, et journalise ce
  qu'elle écrit (`CBZ écrit : … (150 pages, 219,0 Mo)`) : l'absence silencieuse de sortie était
  indiagnosticable.
- `pages_clean/` n'est plus annoncé en tête des sorties quand `"images"` n'est pas demandé.
- **Le PDF de 150 planches coûte ~1,2 Go de mémoire, et il n'y a pas de contournement propre
  avec Pillow seul.** Les trois voies ont été mesurées : un seul `save(append_images=…)` donne
  un PDF **correct** (`/Count 150`) au prix de 1,2 Go ; `append=True` page par page **échoue**
  (`PdfFormatError: trailer loop found` — Pillow 12.2.0 plafonne à **3 appends**,
  indépendamment du nombre de pages) ; et `append=True` par lots produit un PDF
  **silencieusement tronqué**, avec un catalogue par lot et `/Count 38` au lieu de 150 — le
  pire des cas, un fichier qui s'ouvre sans erreur en ayant perdu 112 planches. Le plan
  prescrivait justement l'écriture incrémentale comme « la seule solution réellement bornée ».
  On garde donc la voie correcte et on rend le coût visible : le pic est estimé avant
  l'écriture et signalé au-delà de 800 Mo, avec `manga.rendu.pdf_largeur_max` comme levier.
  Les tests vérifient désormais le **nombre de pages déclaré par le catalogue**, pas seulement
  la taille du fichier — c'est ce contrôle manquant qui avait laissé passer la troncature.
- **Le passage à la coupe X-Y aurait invalidé tous les checkpoints.** `regions.json` porte
  maintenant un `format` (v2), et `ocr.json`/`traduction.json` s'alignent **par position** sur
  l'ordre de lecture. Plutôt que d'invalider — ce qui, par le graphe de dépendances, aurait
  entraîné re-détection, re-OCR et re-traduction de tout le tome, soit des heures de GPU et le
  modèle ONNX à nouveau requis — `checkpoints.migrate_page()` **réordonne** : il recalcule
  l'ordre, en déduit la permutation et l'applique aussi aux textes. Les 150 pages du tome ont
  été migrées sans rien recalculer.
- **`manga/typeset.py` réécrit.** Trois défauts corrigés : on composait dans la **bbox** et
  non dans la bulle (une bulle de la page 60 fait 281 px de large au centre mais 53 px en
  haut — le texte débordait aux extrémités) ; la largeur était estimée en **nombre de
  caractères**, sans crénage ; et le repli renvoyait `min_size` **sans revérifier que ça
  tenait**, ce qui, avec le `fill=(0,0,0)` en dur, donnait du texte noir hors de la bulle.
  Désormais : profil de largeur mesuré dans le masque, `min` du profil sur toute la hauteur
  de ligne (c'est lui qui empêche le débordement dans les coins arrondis), habillage
  équilibré par programmation dynamique à pénalité quadratique, métriques réelles via
  `font.getmetrics()`, recherche dichotomique de la taille, et deux `lru_cache` qui
  suppriment ~800 ouvertures de fichier de police par tome.
- **Largeur utilisable = `2 × min(cx − x0, x1 − cx)`**, et non la largeur de la plage
  contiguë : le texte est centré sur `cx`, or la plage ne l'est pas forcément. Trouvé au
  contrôle visuel — « comprends » ressortait tronqué en « mprends » page 60.
- **La taille de police n'est plus simplement maximisée.** Dans une bulle étroite, la plus
  grande taille qui « tient » ne laisse la place que d'un mot par ligne : page 20, « Un rappel
  dès le premier jour ?! » sortait en sept lignes d'un mot, exactement le défaut que
  l'habillage équilibré ne peut pas corriger seul. On explore vers le bas dans une fenêtre
  bornée (72 % de la taille maximale) et on retient le minimum de lignes orphelines. Mesuré
  sur le tome : **3364 → 2671 lignes** (−21 %, bulles bien mieux remplies) et **542 → 472**
  lignes d'un seul mot.
- **Le texte est découpé à l'intérieur de la bulle**, miroir du `paint &= region.mask` de
  `clean.py`. Indispensable pour le cas qu'aucun habillage ne résout : un mot insécable plus
  large que la bulle (URL, nom propre à rallonge). Mesuré sur les 150 planches : **0 pixel de
  texte hors des masques**.
- **Harmonisation des tailles par planche** : plafond = médiane × 1,25, les bulles au-dessus
  sont recalculées, **jamais** les petites agrandies (une bulle est petite parce qu'elle est
  étroite). Mesuré : **0 page sur 124** dépasse le ratio.
- **Fin de la troncature silencieuse** : `zip(regions, texts)` laissait les dernières bulles
  vides quand `_parse_translations` renvoyait une liste plus courte. La longueur est
  contrôlée, complétée, et l'écart remonté. Les débordements (14 sur le tome) sont signalés
  page et bulle à l'appui — jamais tronqués, jamais résolus en agrandissant la bulle.

## [0.9.0] - 2026-08-13

Première version numérotée. La brique **light novel est stable** (utilisée en production
sur plusieurs tomes) ; la brique **manga est en bêta** — son rendu est en cours de remise
à niveau (voir « Limites connues » du README §12).

### Ajouté

- `core/version.py` : source unique de vérité de la version, avec `ETAT_BRIQUES` qui
  distingue le degré de confiance des deux briques (`ln: stable`, `manga: bêta`).
- Ce `CHANGELOG.md`, et sa règle de numérotation propre au projet : ce qui déclenche un
  MAJEUR ici, c'est l'invalidation d'un cache — une relance de tome coûte des heures de
  GPU, pas quelques secondes de compilation.
- `--version` sur les deux CLI (`run.py`, `run_manga.py`) ; côté manga, la sortie
  suffixe `(brique manga : bêta)`.
- La version est désormais tracée sur toutes les surfaces durables : en-tête de run des
  deux pipelines, ligne d'en-tête de `perf.log` (avec date et commande), entrée
  `- Version :` dans `RAPPORT.md`, commentaire HTML en tête du Markdown assemblé (rejoué
  tel quel par `--render-only`), et métadonnées des fichiers livrés — `cp:keywords` en
  DOCX, `dc:subject` en EPUB — pour qu'un `.docx` qui circule seul dise encore quelle
  version l'a produit.
- `tests/test_version.py` : garde-fou contre la dérive entre `__version__` et le
  CHANGELOG.

### Corrigé

- **Les métadonnées de version n'atteignaient pas les fichiers livrés** par la voie
  attendue : sur Pandoc 3.10, `--metadata keywords="…"` est **silencieusement ignoré**
  par le writer DOCX (qui attend une *liste*, pas une chaîne — `cp:keywords` ressortait
  vide), et le writer EPUB ne lit pas `keywords` mais `subject`. L'empreinte passe donc
  par un bloc YAML en tête du `.render.md` temporaire, qui exprime les deux en liste.
  Trois tests verrouillent le comportement, dont un test d'intégration avec le vrai
  Pandoc — le seul capable d'attraper ce genre de no-op muet.
- **`.gitignore` était entièrement inerte** : encodé en UTF-16LE avec BOM, que git ne
  décode pas (`git check-ignore -v build/` sortait en erreur). Conséquence mesurée :
  **3347 fichiers suivis**, dont 2549 sous `build/` et 654 sous `sources/` (les scans
  eux-mêmes), pour un dépôt de 1,2 Go sur un seul commit. Réécrit en UTF-8 sans BOM ;
  l'index retombe à **81 fichiers** (le code, les tests, les prompts, les gabarits et le
  projet de démonstration `sources/Demo LN/`).
- L'exception du projet de démonstration est écrite `sources/*` puis
  `!sources/Demo LN/`, et **non** `sources/` : git refuse de ré-inclure quoi que ce soit
  sous un répertoire exclu en bloc, ce qui aurait dé-suivi en silence le projet dont
  dépend `python run.py "Demo LN" Vol.1 --dry-run` (README §11).
