# Le run se regarde — ce que la barre disait, et ce qu'elle dit

**Lot 32** (`PLAN-32-LE-RUN-SE-REGARDE.md`) · livré en **2.26.0** · relevé du **2026-09-05**,
sur le PC principal.

| | |
|---|---|
| Commit de départ | `5b781dc` (2.25.1) |
| Machine | Windows 11 Pro 10.0.26200, Python 3.12.3, PySide6 6.11.1 / Qt 6.11.1 |
| Corpus | les **24 `perf.log`** de `build/` — 11 côté light novel, 9 côté manga, 3 côté illustration, 1 côté OCR de scans. **18 fichiers** portent au moins un run exploitable, pour **36 runs** au total (23 manga, 13 light novel) ; les trois logs d'illustration et celui de l'OCR n'écrivent pas de ligne d'avancement |
| Empreinte de `config.yaml` | **inchangée** — le lot n'y touche pas une ligne |
| Outils de mesure | `tools/tracer_progression.py` et `tools/banc_progression.py`, livrés par ce lot |

Reproduire, des deux côtés du lot :

```powershell
python tools/tracer_progression.py --markdown --rejouer --analyser tests/corpus/progression/*.jsonl
python tools/tracer_progression.py --markdown --anonyme --depuis-perf build/*/*/manga/perf.log
python tools/tracer_progression.py --markdown --anonyme --depuis-perf build/*/*/perf.log
python tools/banc_progression.py --markdown
```

⚠ **Les œuvres ne sont pas nommées.** Le corpus est sous droit d'auteur et la série 31-37
l'écrit : « aucune œuvre du corpus dans une capture, un rapport ou un artefact ». Les tables
ci-dessous sont produites avec `--anonyme`, et les trois traces versionnées sous
`tests/corpus/progression/` ne contiennent que des index de planche et des noms de fichiers
générés (`page_0084.png`) — jamais un titre.

---

## 0. Le résumé, pour qui ne lira que ça

| | avant | après |
|---|---:|---:|
| reculs de la barre, sur un tome light novel de 25 chapitres | **66** | **0** |
| dénominateurs distincts vus dans ce même run | **6** | **1** |
| part de ce run de 12 h **sans temps restant affichable** | **89,7 %** | **6,9 %** |
| part d'un run manga de 150 planches sans temps restant | 2,6 % | **1,7 %** |
| part d'une bande webtoon de 9 planches sans temps restant | 44,2 % | **27,6 %** |
| phases de run qui portent un poids de temps **mesuré et utilisable** | — | **1 sur 7** |
| pourcentage affiché par l'interface | `%p%` sur un dénominateur changeant | **aucun** |

Deux de ces lignes sont des résultats **négatifs**, et elles comptent autant que les autres :
la mesure du poids des phases ne soutient pas le modèle pondéré que le plan envisageait, et
le pourcentage disparaît de l'écran plutôt que de rester faux. Le § 3 les défend.

---

## 1. Étape 0.1 — la trace du canal, brique par brique

### 1.1 Comment les traces ont été obtenues, et ce que ça change

Le plan demandait « un enregistreur temporaire (un `Reporter` décorateur qui journalise
`(horodatage, méthode, arguments)` en JSONL) » et **trois runs réels**. L'enregistreur existe
(`tools/tracer_progression.Enregistreur`) et il est testé. Mais relancer trois runs réels
coûte, sur ce corpus, plusieurs heures de GPU et un appel LLM par lot — pour un lot dont
`PLAN-32` §4 dit lui-même qu'« il observe ».

⚠ **Les traces publiées sont donc RECONSTRUITES depuis les `perf.log` du dépôt, et il faut
savoir ce que ça vaut.** Ce qui est réel : l'ordre des planches, l'ordre des phases, la durée
de chaque étape, les sauts de cache, les reprises. Le `perf.log` est écrit à chaque run par
`core/cli.make_reporter` — « le flag `--verbose` ne décide que de l'AFFICHAGE » — et il porte
une ligne par planche et par étape. Ce qui est déduit : le couple `stage` + `progres` qui
précède chaque groupe de lignes, parce que le code le pose là (`orchestrator_manga` L894-895
et L1614-1616) ; et le canal `phase`, qui **n'existait pas** avant ce lot et dont les
frontières sont posées là où le code les pose.

Ce que la mesure **ne dit pas** :

- **rien du temps non instrumenté** — lecture du plan, migration de cache, assemblage CBZ,
  export docx, rendu Pandoc. Aucune ligne de perf ne les couvre, donc les durées ci-dessous
  sont des durées de *temps instrumenté*, systématiquement plus courtes que l'horloge ;
- **rien d'une autre machine**, ni d'une seule version. Les 24 `perf.log` viennent d'une
  seule machine, mais de **douze versions** différentes — de la 0.29.0 à la 2.20.0. Les
  parts du § 2 mélangent donc des runs dont les coûts ont bougé entre-temps, et c'est une
  des raisons possibles des écarts qui font échouer la règle du facteur 3 ;
- **rien d'un run manga neuf de bout en bout sur chaque volume**. Plusieurs tomes ont été
  traités par étapes successives, et le § 2 traite les deux natures séparément ;
- **rien de l'écran**. La trace porte le canal, pas ce que l'utilisateur regardait.

### 1.2 Les trois traces demandées

Versionnées sous `tests/corpus/progression/`, et rejouées par
`tests/test_core_progression.py` à chaque exécution de la suite.

| trace | ce que c'est | événements | durée instrumentée |
|---|---|--:|--:|
| `manga-pagine` | un tome manga paginé, **150 planches**, run complet | 756 | 2 397 s |
| `bande-webtoon` | la seule bande webtoon du corpus, **9 planches** | 51 | 362 s |
| `light-novel` | un tome light novel, **25 chapitres** | 314 | 44 147 s |

**Avant le lot** — ce que la barre voyait, c'est-à-dire un compteur unique nourri par
`progres`, `chapter`, `block` et le repli par expression régulière sur `stage` :

| trace | avancements | reculs | dénominateurs distincts | sans ETA affichable | part |
|---|--:|--:|--:|--:|--:|
| manga paginé | 750 | **2** | 1 | 63 s | 2,6 % |
| bande webtoon | 45 | **2** | 1 | 160 s | 44,2 % |
| light novel | 211 | **66** | **6** | **39 635 s** | **89,7 %** |

**Après le lot** — les mêmes traces rejouées dans `core/progression.py` :

| trace | points | reculs de fraction | indéterminés | sans ETA affichable | part |
|---|--:|--:|--:|--:|--:|
| manga paginé | 752 | **0** | 4 | 40 s | 1,7 % |
| bande webtoon | 47 | **0** | 4 | 100 s | 27,6 % |
| light novel | 313 | **0** | 1 | 3 063 s | **6,9 %** |

Les « indéterminés » sont les instants où la fraction se tait plutôt que d'inventer : la
préparation, le chargement du modèle de détection, et chaque lot de traduction en vol. Ils
sont **quatre** sur un tome de 150 planches, contre une barre qui prétendait savoir en
permanence.

### 1.3 Le chiffre qui décide, et il décide dans l'autre sens que prévu

Le plan est explicite : « **C'est ce dernier chiffre qui justifie le lot ou l'enterre.** S'il
est de 30 s sur un run de trois heures, il n'y a pas de sujet et il faut l'écrire. »

Il n'est pas de 30 s. Sur le light novel, **onze heures d'un run de douze n'affichaient aucune
estimation** — 89,7 %. Et le plan se trompait sur la cause : il attendait le coût de deux
changements de régime × 4 planches côté manga. Côté manga, c'est bien ce qu'on trouve, et
c'est effectivement négligeable — 1,9 % à 2,6 % d'un run de 40 minutes. **Le défaut grave est
côté light novel, et le plan ne l'avait pas vu.**

La cause est nommable en une ligne : `ReporterQt.block` émettait la progression. Un bloc
redémarre à 1 **à chaque étage de chaque chapitre**, si bien que la barre alternait entre le
compte des chapitres (`1/25`) et celui des blocs (`3/10`), et que `Estimateur.noter` vidait sa
fenêtre à chaque alternance — puis redemandait ses `MINIMUM = 4` points, qu'il n'avait
jamais le temps d'accumuler.

### 1.4 Le corpus entier, pour que trois traces ne soient pas trois anecdotes

**Manga — 23 runs empilés dans 9 fichiers.** Les runs à 100 % sans ETA sont des reprises très
courtes (une à trois planches) : le sujet n'est pas là.

| runs | reculs, médiane | reculs, pire | dénominateurs distincts | part sans ETA, médiane | pire |
|--:|--:|--:|--:|--:|--:|
| 23 | 1 | 2 | **1 partout** | 37,9 % | 100 % |

**Light novel — 13 runs empilés dans 11 fichiers.**

| runs | reculs, médiane | reculs, pire | dénominateurs, médiane | part sans ETA, médiane | pire |
|--:|--:|--:|--:|--:|--:|
| 13 | **15** | **135** | **6** (jusqu'à **13**) | **53,3 %** | **100 %** |

Le pire cas côté light novel est un run de **15 h 26** dont **14 h 59 sans estimation** — soit
**97,2 %** —, avec **132 reculs** et **5** dénominateurs distincts. Le détail run par run est reproductible avec les deux commandes anonymes en
tête de document.

---

## 2. Étape 0.2 — le poids des phases, et pourquoi il n'est pas armé

### 2.1 Ce qu'on mesure, et à quelle granularité

Une phase de progression n'est pas une ligne de `perf.log`. L'orchestrateur ne peut pas
annoncer « détection » puis « nettoyage » puis « OCR » : il les paie **planche par planche,
dans le même balayage**, et une phase qui oscille n'est pas une phase. Ce qui est monotone,
ce sont les balayages — et ce sont eux que `Reporter.phase` annonce.

Le regroupement change aussi la mesure, dans le bon sens : détection, nettoyage, OCR et SFX se
compensent l'un l'autre d'un tome à l'autre, si bien que leur somme est **trois fois plus
stable** que chacun pris à part.

### 2.2 Run neuf — la table qui décide

**Manga, 14 runs neufs, 6,1 h de temps instrumenté.**

| phase | part médiane | n runs | min | max | écart | poids retenu |
|---|--:|--:|--:|--:|--:|---|
| analyse (balayage A) | 32,4 % | 14 | 25,3 % | 40,3 % | ×1,6 | **32,4 %** |
| terminologie | 4,9 % | 11 | 1,2 % | 23,1 % | ×18,8 | **aucun** |
| traduction | 27,9 % | 14 | 10,7 % | 48,1 % | ×4,5 | **aucun** |
| rendu | 34,2 % | 14 | 17,9 % | 57,0 % | ×3,2 | **aucun** |

**Light novel, 11 runs neufs, 83,8 h de temps instrumenté.**

| phase | part médiane | n runs | min | max | écart | poids retenu |
|---|--:|--:|--:|--:|--:|---|
| terminologie | 25,6 % | 11 | 13,4 % | 49,7 % | ×3,7 | **aucun** |
| traduction | 64,8 % | 11 | 16,8 % | 77,0 % | ×4,6 | **aucun** |
| mise en page | 9,6 % | 11 | 4,7 % | 17,6 % | ×3,8 | **aucun** |

Le détail par étage (détection, nettoyage, OCR, SFX, glossariste, correction, révision,
cohérence) est rendu par le même outil et n'améliore rien : `detection` monte à ×5,0 et
`glossariste` à ×10,0.

### 2.3 Run de reprise — deux tableaux, comme demandé

**Manga, 9 runs de reprise, 0,4 h.** Le tableau est publié, mais il ne soutient **aucun**
poids, et pas pour la raison qu'on croit : la plupart de ces runs ne paient qu'**une seule**
phase. Un `--from rendu` a donc un « rendu » à 100 % de son temps instrumenté, et une médiane
sur `n = 1` n'est pas une médiane.

| phase | part médiane | n runs | écart | poids retenu |
|---|--:|--:|--:|---|
| rendu | 100,0 % | 7 | ×44,5 | **aucun** |
| traduction | 50,0 % | 3 | ×1,7 | *passe la règle, mais n = 3 sur une seule œuvre* |
| glossariste | 19,5 % | 3 | ×3,6 | **aucun** |
| detection / ocr / sfx / terminologie | — | 1 chacune | — | **aucun** |

**Light novel, 2 runs de reprise, 11,4 h** — les deux ne paient que la terminologie.
`n = 2` : le second tableau n'a **pas assez d'échantillons**, et c'est la réponse que le plan
autorisait explicitement.

### 2.4 Le verdict, et il est négatif

> ⚠ Si l'écart min-max d'une phase dépasse un facteur 3, cette phase n'a pas de poids
> utilisable.

**Une phase sur sept passe la règle** — le balayage A du manga, à ×1,6. Une phase pondérée sur
sept ne fait pas un modèle pondéré : la fraction de temps qu'on en tirerait serait juste sur un
tiers du run et inventée sur les deux autres.

Les poids sont donc **conservés et désarmés**. `core/progression.POIDS_MESURES` porte la
mesure avec son `n` et son écart, `Phase.poids` vaut `None` partout, et
`tests/test_core_progression.py::test_aucun_jeu_de_phases_du_depot_n_est_pondere` garde
l'état. Le jour où une mesure armera des poids, ce test tombera — et ce sera le bon moment
pour relire cette page.

C'est le même arbitrage que les « trois réglages désarmés » de
`docs/mesures/webtoon-2026-08-26.md` : livrer le chemin complet, avec la mesure qui explique
pourquoi sa condition d'entrée n'est pas remplie.

---

## 3. La décision qui découle de la mesure : compté plutôt que pondéré

Sans poids, que reste-t-il ? Le plan répond : « on n'invente pas un pourcentage, on affiche
l'avancement **compté** (« planche 42 sur 131, phase traduction ») et la barre reste sur le
compte d'objets, pas sur un temps. »

`core/progression.py` distingue donc deux natures de fraction, et `nature()` dit laquelle :

- **pondérée** — une part du TEMPS, tirée de poids mesurés. Le chemin existe, il est testé
  (`test_des_poids_mesures_donneraient_une_fraction_ponderee`), et **aucun run de ce dépôt ne
  l'emprunte** ;
- **comptée** — une part des OBJETS traversés, à partir d'un fait de structure : le balayage
  A visite chaque planche une fois, la passe terminologique aussi, le balayage B aussi. Ce
  n'est pas une mesure de temps, ce n'est pas non plus un poids inventé.

### Trois conséquences visibles à l'écran

1. **Aucun pourcentage n'est affiché nulle part.** Ni dans le bandeau, ni dans le titre de
   fenêtre. « 64 % » se lirait comme 64 % du temps, alors que la moitié des planches du
   balayage A ne coûte que ~32 % du run — c'est la mesure du § 2.2 qui l'interdit. Le compte,
   lui, porte son dénominateur : « planche 84 / 131 ». C'est la règle des chiffres du dépôt,
   appliquée à l'interface.
2. **La barre reste déterminée** tant que le compte est connu, parce qu'elle mesure des
   objets et qu'ils sont bornés — « determinate whenever the operation is bounded, even if
   duration cannot be accurately predicted ».
3. **Le temps restant reste affiché**, parce qu'il vient du débit OBSERVÉ de l'unité comptée
   (`gui/avancement.Estimateur`, fenêtre glissante de 12, minimum 4), et non d'une conversion
   d'un poids en secondes. C'est exactement ce que ce module fait depuis le lot 20 ; ce lot
   lui donne seulement un débit qui ne recule plus.

### Ce que cette décision coûte

Un utilisateur qui regardait « 42 % » ne le verra plus. Il verra « planche 84 / 131 · phase
Traduction et rendu (5/6) · ~1 h 10 restantes ». C'est un changement de sortie assumé, et il
est dans le CHANGELOG.

---

## 4. Ce que le lot a mesuré en chemin, et qui n'était pas dans le plan

**La passe terminologique du manga était entièrement muette.** `_passe_terminologie` n'appelle
ni `stage` ni `progres` — 150 appels LLM pendant lesquels la barre ne bougeait pas d'un pixel.
Elle vaut de 1,2 % à 23,1 % du temps instrumenté d'un run neuf (médiane 4,9 %, n = 11). Une
barre immobile pendant vingt minutes est indiscernable d'un blocage. Elle est instrumentée par
ce lot, et c'est la seule ligne de `progres` que le lot AJOUTE dans une boucle qui n'en avait
pas.

**Le `perf.log` de deux volumes manga du corpus ne contient aucune ligne de traduction ni de
rendu.** Ces deux tomes ont été traités en `--extract-glossary` seulement. Ils sont donc
exclus des tableaux de poids par `est_neuf`, ce qui est le comportement voulu, mais il fallait
le dire : le corpus manga « neuf » compte 14 runs, pas 23.

---

## 5. La barre des tâches Windows — la question est tranchée : **rien**

`PLAN-32` L32.4(b) demandait de vérifier l'état, de mesurer le coût, et autorisait
explicitement un « non ».

**Constat du 2026-09-05, sur l'installation de développement.** PySide6 **6.11.1**, Qt
**6.11.1**. Les 64 modules livrés par `pkgutil.iter_modules(PySide6.__path__)` ne contiennent
**pas** `QtWinExtras` — le module a été retiré de Qt 6, et `QWinTaskbarProgress` avec lui.

```powershell
python -c "import PySide6, pkgutil; print(PySide6.__version__, 'QtWinExtras' in {m.name for m in pkgutil.iter_modules(PySide6.__path__)})"
#   → 6.11.1 False
```

Trois options restaient, et deux sont écartées par le plan lui-même :

| option | coût | verdict |
|---|---|---|
| `ITaskbarList3` par `ctypes` | du COM Windows-spécifique dans `gui/`, dans un dépôt qui garde Linux et macOS en ligne de mire (`PLAN-20`), **pour un confort** | refusée |
| une dépendance tierce | « aucune dépendance tierce ajoutée pour ce confort » (`PLAN-32` critère 7) | refusée |
| rien | le titre de fenêtre porte déjà l'avancement, et la barre des tâches affiche le titre | **retenue** |

C'est précisément l'usage que Microsoft prête au titre : « optimize the title for display on
the taskbar by concisely placing the distinguishing information first ». Le titre devient
`84/131 — Manga · Mon Manga / Vol.2 — Angelith 2.26.0 [*]`.

⚠ La décision est écrite **avec sa date et sa version** en tête de `gui/bandeau.py`, et
`tests/test_gui_bandeau.py::test_qtwinextras_n_existe_toujours_pas` la re-vérifie à chaque
exécution de la suite. Le jour où PySide6 relivre le module, le test tombe avec un message qui
renvoie ici — c'est la règle des affirmations d'état (§ 5 bis du contexte agent), appliquée à
une décision plutôt qu'à un commentaire.

---

## 6. Les onze critères du plan, un par un

| # | Critère | Verdict |
|--:|---|---|
| 1 | Trois traces JSONL publiées, avec reculs, dénominateurs et secondes sans ETA, par brique | **tenu** — § 1.2, traces versionnées sous `tests/corpus/progression/` |
| 2 | Tableau de poids avec `n` et écart min-max ; toute phase au-delà de ×3 livrée **sans poids**, et c'est écrit | **tenu** — § 2.2 à § 2.4. Six phases de progression sur sept sont sans poids, et la septième aussi, parce qu'une seule ne suffit pas |
| 3 | `core/progression.py` sans Qt ni horloge murale ; un test rejoue les traces réelles et asserte que `fraction()` ne décroît jamais ; ce test échouait avant le lot | **tenu** — `tests/test_core_progression.py`. Le jumeau `test_le_canal_brut_recule_avant_le_lot` mesure l'état d'avant sur la même trace : 66 reculs |
| 4 | Sortie console d'un `--dry-run` identique avant/après, comparée octet pour octet | **tenu** — `tests/test_manga_runtime.py::test_la_sortie_console_dun_dry_run_est_identique_octet_pour_octet`, sur un vrai `process_volume` |
| 5 | Le bandeau affiche phase (i/n), objet, avancement compté et temps restant ; jamais de % ni d'ETA sur une fraction indéterminée, testé sur les trois cas de L32.6 | **tenu** — `tests/test_gui_avancement.py`, paramétré sur les trois cas. ⚠ **Il n'affiche jamais de pourcentage du tout**, et le § 3 dit pourquoi |
| 6 | Le titre porte l'avancement en tête sans casser `[*]` ; les quatre combinaisons testées | **tenu** — `test_le_titre_garde_la_marque_de_modification`. ⚠ Le titre porte `84/131`, pas `66 %` : même motif qu'au critère 5 |
| 7 | La barre des tâches est tranchée par écrit ; aucune dépendance tierce | **tenu** — § 5, décision « rien », datée et gardée par un test |
| 8 | Aucune boîte modale à la fin d'un run ; la notification système, si livrée, désarmée par défaut | **tenu** — `test_la_fin_du_run_laisse_un_bilan_et_aucune_modale`. ⚠ **Aucune notification système n'est livrée** : le bandeau porte l'état terminal, et `QSystemTrayIcon` aurait été un réglage de plus pour un besoin déjà couvert |
| 9 | `progression_de_stage` et son test existent toujours ; les étapes non instrumentées avancent encore la barre | **tenu** — `test_le_repli_par_libelle_avance_encore_la_barre`, et `tests/test_gui_reporter.py` est inchangé |
| 10 | `ruff check .` passe ; `pytest -q -m "not modeles and not lent"` passe sans modèle, sans GPU, sans endpoint LLM | **tenu** — cf. § 7 |
| 11 | Ce document reprend les critères un par un, y compris les non tenus, et dit ce que la mesure ne dit pas | **tenu** — vous le lisez ; § 1.1 porte les limites |

### Ce que le lot n'a PAS fait, et qui était dans le plan

- **`QSystemTrayIcon.showMessage` n'est pas livrée.** Le plan l'autorisait « si elle est
  optionnelle et désarmée par défaut ». Un réglage désarmé par défaut est un réglage que
  personne n'active, et l'état terminal du bandeau couvre le besoin qui la motivait — « un run
  de nuit qui finit à 3 h du matin ne laisse qu'une ligne dans un journal replié ». Elle
  reste possible ; elle n'est pas nécessaire aujourd'hui.
- **Le journal n'est pas filtré en place.** L32.5 demandait « un bouton qui déplie le journal
  filtré sur les avertissements ». Le bouton existe et il ouvre les avertissements du run dans
  un `DialogueTexte` — le journal, lui, reste entier et à sa place, parce qu'il est le seul
  endroit où l'on relit ce qui s'est passé **dans l'ordre, avec ce qui l'entourait**. Filtrer
  en place aurait demandé de restructurer le `QPlainTextEdit` du journal, ce qui est hors du
  périmètre d'un lot qui « observe ».
- **`illustration/progression.py` n'est pas fusionné**, comme demandé. `PHASES_ILLUSTRATION`
  reprend seulement ses trois identifiants pour que le bandeau sache les nommer, et
  `AtelierIllustration.etat_progression()` est une façade de lecture. Les deux modèles
  cohabitent, et ce n'est pas une dette.
- **Le bandeau ne disparaît pas TOUT SEUL à la fin d'un run**, alors que L32.3 (5) dit « il
  disparaît quand aucun run ne tourne » et que L32.5 demande un état terminal persistant. Les
  deux ne peuvent pas être vrais en même temps. Le bilan reste, avec un bouton « Fermer » qui
  le retire — plutôt qu'un délai, qui aurait fait disparaître au bout de N secondes le
  résultat d'un run de nuit que personne n'a encore lu. Le bandeau reste invisible tant
  qu'aucun run n'a commencé, ce qui est l'esprit de la règle : pas de décor permanent.

### Deux défauts trouvés en câblant, et corrigés dans le lot

- **Le bouton « Arrêter proprement » du bandeau aurait écrit un `STOP` dans le mauvais
  dossier.** Le bandeau sert les deux briques, mais elles ne s'arrêtent pas par le même
  chemin : un orchestrateur lit un fichier `STOP` sous son `build/`, l'atelier d'illustration
  relit un drapeau entre deux images (« un modèle interrompu en plein débruitage laisse le
  pilote dans un mauvais état »). Un `STOP` écrit pendant une génération d'image n'aurait rien
  arrêté — et aurait interrompu le **prochain** run manga à son démarrage.
  `AtelierIllustration.demander_arret()` devient public, et `Fenetre._arreter_run` route sur
  le genre de la tâche en cours.
- **Une tâche hors tome aurait porté le nom du run précédent.** Un import de glossaire, une
  copie de sources et un diagnostic portent eux aussi `planche=None`, donc passent par le
  bandeau — mais `_cible_run` garde le tome du run d'avant. Ces genres sont désormais nommés
  par le libellé de leur tâche, et ne se voient proposer aucun arrêt : ils n'ont pas de
  frontière propre.

---

## 7. Le compte de tests

Toutes dépendances optionnelles installées, `python -m pytest --collect-only -q` :

| | avec PySide6 | sans PySide6 | écart |
|---|---:|---:|---:|
| avant le lot (2.25.1) | 4 130 | 3 864 | 266 |
| **après le lot (2.26.0)** | **4 239** | **3 947** | **292** |

Le lot ajoute **109 tests**, dont **83 sans Qt** — c'est la proportion attendue d'un lot dont
le cœur (`core/progression.py`, `gui/avancement.py`, les deux outils) est en Python nu.
L'écart passe de 266 à 292 : les 26 tests d'interface neufs sont ceux de `gui/bandeau.py` et
du câblage de la fenêtre.

⚠ **Une partie de ces 83 tests sans Qt n'est pas neuve, elle est LIBÉRÉE.**
`progression_de_stage` a déménagé de `gui/travailleur.py` (qui importe Qt) vers
`core/progression.py` : la fonction n'a pas changé d'une ligne, son test d'origine non plus,
mais le rejeu des traces réelles peut désormais tourner sans PySide6 — ce que la règle de
couche du dépôt demandait déjà et que l'emplacement empêchait de prouver.

Reproduire la colonne de droite :
`python -m pytest --collect-only -q -p tools.compte_sans_pyside`.

La boucle courte (`-m "not modeles and not lent"`) en exécute **4 182**, les mêmes 57 restant
désélectionnés par `lent` / `modeles`.

---

## 8. Ce que la mesure ne dit pas, en un paragraphe

Elle ne dit rien de la **perception**. Aucun de ces chiffres ne prouve qu'un utilisateur
comprend mieux où en est son run : ce sont des propriétés du canal et du modèle, pas des
résultats d'usage. Elle ne dit rien non plus des runs qui **échouent** — toutes les traces
publiées viennent de runs qui se sont terminés, et le comportement du bandeau sur un arrêt
propre en plein lot n'est vérifié que par des tests, pas par un relevé. Elle ne dit rien,
enfin, du coût d'affichage : le bandeau se repeint à chaque avancement, soit ~750 fois sur un
tome de 150 planches, et personne n'a mesuré ce que ça coûte — c'est de l'ordre de la
microseconde par repeinte, mais « de l'ordre de » n'est pas une mesure.
