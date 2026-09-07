# PLAN 35 — La retouche devient une destination : le tome reçu, la garde déplacée, la bande

> **Lire `00-CONTEXTE-AGENT.md`, puis `README-INTERFACE-31-37.md`.**
>
> **Nature attendue** — **CORRECTIF + MINEUR**. Le correctif est L35.4 : le `PLAN-31` ouvre un
> trou dans la garde du travail non enregistré, et ce lot le referme. Le mineur est L35.3.
>
> **Charge estimée** — 7 jours. Le panneau existe et il est mûr ; l'essentiel du travail est de
> le **découpler**, pas de l'étendre.
>
> **Prérequis : `PLAN-31`** (obligatoire — c'est lui qui crée la destination). Le `PLAN-34` n'est
> pas requis, mais L35.2 est plus utile après lui.
>
> ⚠ **`gui/editeur.py` pèse 107 206 octets et fonctionne.** Le risque de ce lot n'est pas de ne
> pas en faire assez, c'est d'en refaire trop. Aucune réécriture d'ergonomie n'est demandée ici.

---

## 1. L'état, relevé à la source le 2026-09-04 (2.24.1, `8e5ee5a`)

### 1.1 Ce que la retouche sait déjà faire

`gui.py` l'annonce, et c'est exact — quatre capacités que la ligne de commande ne peut pas
donner :

- **voir** les zones de bulles superposées à la planche, avec leur numéro d'ordre de lecture,
  « l'ordre qui aligne `ocr.json` et `traduction.json`, et dont une inversion est invisible sur
  la page rendue » ;
- **corriger** une zone manquée, mal découpée ou inventée (ajouter, redessiner, supprimer,
  scinder) sans Photoshop et sans éditer de JSON ;
- **retoucher** une réplique au clavier — elle part dans `traduction_manuelle.json`, que le
  pipeline ne réécrit jamais ;
- **relettrer** la planche d'un bouton et regarder le résultat.

Les fichiers : `editeur.py` (107 Ko), `editeur_zones.py` (25 Ko), `editeur_apercus.py` (15 Ko),
`scene_planche.py` (43 Ko), `pellicule.py` (13 Ko), `apercu.py` (15 Ko),
`cache_apercu.py` (8 Ko). Et un verrou **par planche**, pas par panneau : la planche traitée est
grisée, les autres restent éditables, et une seconde demande sur une planche occupée est **mise
en file**, jamais refusée par une boîte de dialogue — « refuser un geste que l'utilisateur vient
de faire est le pire des retours ».

### 1.2 Les cinq attaches qui la retiennent à la fenêtre

C'est la liste de travail de ce lot, relevée dans `gui/fenetre.py` :

| Attache | Ligne | Ce qu'elle fait |
|---|---:|---|
| le tome vient des combos de la barre haute | L189-201, L445 | `_ouvrir_tome` construit et pousse dans l'éditeur |
| la garde est armée sur le changement de combo | L480 `_garde_changement_de_tome` | protège le travail non enregistré |
| `Services` est construit par la fenêtre | L466-468 | un par tome, libéré au changement |
| les fils sont branchés par la fenêtre | L157-163, L471 `editeur.brancher` | fil de travail, fil de lecture, fenêtre d'aperçus |
| le verrou vient des signaux de la fenêtre | L778 `_sur_debut`, L796 `_sur_fin` | relais vers `marquer_verrou` |

**Trois de ces cinq doivent rester à la fenêtre** (les fils, `Services`, le relais de verrou) —
c'est la conclusion du `PLAN-31` L31.4, et elle est motivée par les trois trous de concurrence
que la 1.1.0 avait laissés. **Deux doivent descendre** : la sélection du tome, et la garde.

### 1.3 Le webtoon dans l'éditeur

Le webtoon est livré depuis la 2.6.0 et l'éditeur le connaît : `webtoon` apparaît dans
`gui/editeur.py`, `gui/scene_planche.py`, `gui/modele_tome.py`, `gui/dialogues.py`. Le sens de
lecture est résolu par `manga/formats.py` (`SENS_PAR_DEFAUT`), et `manga/bubbles_split.py` gère
le découpage.

Ce que la mesure dit du cas difficile, et il est unique dans le corpus :

- une bande de chapitre fait **1080×10 000** ; `config.yaml` (~L1521) le dit sans détour :
  « sur un webtoon, *la planche* est une bande d'un chapitre entier » ;
- le coût mémoire d'un masque est de **10,8 Mo sur une bande 1080×10 000** contre bien moins sur
  une planche 1125×1600 (`config.yaml` ~L894) ;
- `fenetre_hauteur: 2160` — « 2× la largeur d'une planche de webtoon » (~L1455) ;
- et le corpus n'a **qu'une** œuvre webtoon, qui est aussi la seule à source latine. Toute
  mesure faite sur elle confond les deux effets, et le dépôt l'écrit partout où il le peut.

---

## 2. Étape 0 — mesurer l'ouverture avant de la déplacer

### 0.1 — Le coût d'ouvrir un tome dans l'éditeur

Le `PLAN-31` étape 0.1 mesure le démarrage ; celui-ci mesure le geste qui reste après lui.
Publiez, sur trois tomes du corpus :

| Tome | Unités | Temps `editeur.ouvrir` | Aperçus composés en 10 s | Cache (Mo) | Pic mémoire (Mo) |
|---|---:|---:|---:|---:|---:|
| un tome paginé « moyen » | ~130 planches | | | | |
| le plus gros tome paginé du corpus | | | | | |
| la bande webtoon (`webtoon A` Chap.11) | 1 bande / chapitre | | | | |

⚠ **La troisième ligne est celle qui compte.** Si l'ouverture de la bande demande plusieurs
secondes ou plusieurs centaines de mégaoctets, L35.3 a un objet ; sinon, L35.3 se réduit à un
constat, et **ce serait un résultat conforme**.

⚠ **Mesurez aussi le plafond de cache en action** : `editeur.cache.plafond` vaut par défaut
120 Mo (`gui.apercu.plafond_mo`), et la fenêtre d'aperçus 10 planches. Une bande unique de
10 000 px de haut ne se compte pas en planches — que fait la fenêtre glissante quand il n'y a
qu'un seul élément à précharger ?

### 0.2 — Ce que la garde protège, cas par cas

Avant de déplacer `_garde_changement_de_tome`, listez **tous** les chemins par lesquels du
travail non écrit peut être perdu, après le `PLAN-31` :

| Chemin | Gardé aujourd'hui ? | Après `PLAN-31` ? |
|---|---|---|
| changer de tome dans le combo | ✅ L480 | à déplacer |
| changer de projet | ✅ (même chemin) | à déplacer |
| **changer de destination** | — n'existait pas | ❌ **trou neuf** |
| fermer la fenêtre | `action_quitter` L1109 | à vérifier |
| lancer un run global | grise les combos, L790 | à vérifier |
| créer un projet par glisser-déposer | `_apres_creation` L856 | à vérifier |

Et vérifiez ce qui **atténue** déjà la perte : `_marquer_modifie` (L926) pose le `[*]` du titre,
affiche le compte de planches non écrites, et l'infobulle de `etiquette_attente` promet « un
miroir de récupération […] toutes les 30 s ». Le minuteur existe — `gui/editeur.py` L103-104,
`_minuteur_brouillons` à `setInterval(30_000)` — et il écrit par `manga/recuperation.py`.
**Vérifiez qu'il écrit vraiment**, sur un tome fabriqué, en relevant le fichier produit : un
plan qui s'appuie sur une promesse de docstring non vérifiée reproduit le défaut du `perf.log`
du lot 20, dont `Reporter._to_log` testait `getattr(self, "_vlog", None)` et sautait **toutes**
les écritures en silence.

---

## L35.1 — L'éditeur reçoit son tome, il ne le prend plus

L'API existe déjà : `editeur.ouvrir(tome)` et `editeur.brancher(fil, services, fil_lecture,
fenetre=…)`. Ce lot supprime la dépendance implicite aux combos de la fenêtre.

Le contrat après le lot :

1. la destination « Retouche » porte **son** sélecteur œuvre/tome, filtré sur les tomes que
   l'éditeur sait ouvrir (les tomes manga et webtoon — `modele_tome._est_tome_manga`), et **dit**
   pourquoi un tome light novel n'y figure pas ;
2. elle **demande** l'ouverture à la fenêtre (un signal `demande_ouverture(projet, tome)`), qui
   reste seule à construire `Tome` et `Services` et à les libérer ;
3. `editeur.ouvrir` n'est appelé qu'à ce moment-là, jamais au démarrage, jamais à la
   construction de la destination.

⚠ **La garde `_tome_precedent` (L451) reste**, pour la raison qu'elle porte : `_remplir_tomes`
vide puis remplit la liste, donc `currentTextChanged` part deux fois, et un run qui se termine
rafraîchit la fenêtre. Le défaut qu'elle referme n'a pas disparu avec les onglets.

## L35.2 — Entrer par l'œuvre

Depuis la bibliothèque (`PLAN-34`), un geste « Retoucher » sur un tome ouvre la destination
Retouche **sur ce tome**. C'est le seul lien que ce lot doit à la bibliothèque, et il se réduit
au même signal que L35.1.

⚠ **Et l'entrée par le run** : `fenetre.py` a déjà `_aller_aux_runs` (L1182), branché sur
`editeur.demande_runs` — le lot 19 a livré ce chemin parce que « *jamais traité* demande un run,
et le geste attendu est maintenant un bouton plutôt qu'une phrase qui nomme un onglet ». Le
chemin inverse doit exister : un run terminé propose la retouche des planches qu'il vient
d'écrire. Le dépôt sait déjà lesquelles — `self._planches_du_run` (L100-104) existe précisément
pour ne pas jeter tout le cache d'aperçus après un relettrage de trois planches (« ~21 aperçus
perdus, soit ~29 s de recomposition pour rien »).

## L35.3 — La bande, selon ce que la mesure dit

**Conditionnel à l'étape 0.1**, et le plan doit pouvoir se conclure par « rien à faire ».

Si l'ouverture de la bande est coûteuse, ce que ce lot a le droit de livrer :

1. une **navigation par segment** dans la bande — la bande reste une seule planche pour le
   pipeline (c'est le contrat de numérotation, on n'y touche pas), et l'éditeur la parcourt par
   fenêtres verticales de hauteur configurable, en réutilisant `fenetre_hauteur` plutôt qu'en
   inventant une seconde notion ;
2. un **aperçu partiel** — composer la portion visible, pas la bande entière ;
3. la **mémoire mesurée** affichée, comme la 2.6.0 l'a fait pour la première fois (`perf.log` +
   `RAPPORT.md`, sans nouvelle dépendance).

Ce qu'il n'a **pas** le droit de faire :

- ⚠ **découper la bande en planches dans le cache.** Ce serait toucher au contrat
  `checkpoints.FORMAT_VERSION`, qui encode le nombre et l'ordre auxquels `ocr.json` et
  `traduction.json` s'alignent **par position** — interdit 1 du contexte agent, et
  `load_regions` rendrait `None` sur écart de version, donc `downstream("detection")` sur
  **tous** les projets. Des heures de GPU pour un confort d'affichage ;
- toucher au sens de lecture ou à l'ordre de numérotation. Le commentaire de `config.yaml`
  L1788 est explicite : supprimer ces réglages « numéroterait les bulles à l'envers sur toute
  la bande, sans un avertissement » ;
- ⚠ **généraliser depuis une seule œuvre.** Le corpus a **une** bande, et elle est aussi le
  seul volume à source latine. Tout chiffre de ce lot le porte.

## L35.4 — La garde suit le geste (le correctif)

Le trou est nommé par le `PLAN-31` L31.0.3 et mesuré par l'étape 0.2 : après la refonte, quitter
la retouche est un **changement de destination**, que rien ne garde.

Ce que le lot livre :

1. la garde devient une **demande de permission de quitter**, portée par la destination :
   `peut_quitter() -> bool`, appelée par la navigation avant tout changement, et par la fermeture
   de fenêtre. Une seule implémentation, plusieurs appelants ;
2. la boîte garde ses trois issues actuelles (enregistrer, jeter, annuler) et son décompte
   (`_boite_travail_en_attente`, L535) ;
3. ⚠ **et un cas neuf à trancher** : peut-on quitter la retouche **sans** fermer le tome, pour
   aller regarder un run, puis revenir ? La réponse honnête est oui — le travail non écrit reste
   en mémoire, le miroir de récupération continue, et **la garde ne doit alors pas se déclencher
   du tout**. Elle ne se déclenche qu'à ce qui perd le travail : changer de tome, fermer la
   fenêtre. Écrivez cette distinction dans le code, avec son test pour chacun des six chemins de
   l'étape 0.2.

⚠ **Un dialogue qui se pose à chaque changement d'onglet est un dialogue qu'on apprend à
cliquer sans lire**, et c'est la façon la plus sûre de perdre du travail avec une garde en
place.

## L35.5 — Le verrou reste, mais il se justifie

Avec des destinations, l'utilisateur peut éditer pendant qu'un run tourne — ce que le lot 18
avait déjà rendu possible par planche. La règle ne change pas : une tâche de genre `run` porte
`planche=None` et **verrouille tout le tome**, parce qu'« un `process_volume` touche à toutes
les planches, éditer sous lui produirait deux vérités sur le même checkpoint ».

Ce que ce lot ajoute : **le motif visible là où le verrou se voit.** Aujourd'hui
`marquer_verrou(planche, libelle, True)` grise avec un libellé ; avec le bandeau du `PLAN-32`,
l'éditeur verrouillé doit dire « verrouillé : run manga en cours sur ce tome — étape traduction,
planche 84/131 » et offrir le seul geste utile : « Arrêter proprement ».

⚠ **Ne remplacez pas le verrou par une mise en file.** La mise en file existe déjà et elle est
la bonne réponse pour une tâche par planche ; pour un run global, mettre une édition en file
ferait attendre l'utilisateur plusieurs heures sans le dire.

## L35.6 — Ce que la destination ne devient pas

Une note à écrire dans la docstring du panneau, parce que ce sera la tentation du prochain lot :

- **la retouche reste manga et webtoon.** Il n'y a pas d'éditeur light novel dans ce dépôt, et en
  esquisser un dans ce lot livrerait une demi-capacité. `gui.py` le dit déjà : « L'ÉDITION […]
  n'a de sens que sur des planches : elle reste au manga » ;
- **la retouche n'invente aucun chemin de traitement.** Tout passe par `manga.edition`,
  `checkpoints.save_traduction_manuelle` et `process_volume(only_page=N,
  restart_from="rendu")` — c'est la promesse de `gui/__init__.py`, et c'est elle qui garantit
  qu'« un tome retouché ici se relance à l'identique avec `run_manga.py` ».

---

## 3. Les critères de ce lot

1. Le tableau de l'étape 0.1 est publié pour trois tomes, dont la bande webtoon, avec temps
   d'ouverture, aperçus, cache et pic mémoire — et le comportement de la fenêtre glissante quand
   le tome n'a qu'une unité.
2. Le tableau des six chemins de perte de l'étape 0.2 est publié, avec l'état de chacun avant et
   après le lot, et la vérification que le miroir de récupération 30 s **existe et écrit**.
3. La destination Retouche porte son propre sélecteur ; `Tome` et `Services` restent construits
   et libérés par la fenêtre ; un test compte les instances et vérifie qu'il n'y en a jamais
   deux.
4. `editeur.ouvrir` n'est appelé par aucun chemin de démarrage. Le test du `PLAN-31` critère 2
   reste vert.
5. `peut_quitter()` a une seule implémentation et six appelants testés. Changer de destination
   **sans** changer de tome ne déclenche aucun dialogue, et un test le prouve.
6. Le verrou de run global affiche son motif, l'étape et l'avancement, et offre « Arrêter
   proprement ». Aucune édition n'est mise en file derrière un run global.
7. `checkpoints.FORMAT_VERSION` est inchangée. Un test vérifie qu'aucun cache du corpus n'est
   invalidé — sur des **copies** des caches réels, comme l'exige le point 7 de la définition de
   « terminé ».
8. Si L35.3 livre une navigation par segment, elle réutilise `fenetre_hauteur` et ne modifie ni
   l'ordre de lecture ni la numérotation ; sinon le constat de mesure est publié et le lot est
   conforme sans elle.
9. Tout chiffre webtoon porte la mention « une seule bande au corpus, également le seul volume à
   source latine ».
10. `tools/captures_gui.py` produit les captures de la destination, sur le tome synthétique.
11. `ruff check .` passe ; `pytest -q -m "not modeles and not lent"` passe.
12. `docs/mesures/retouche-<date>.md` reprend ces critères un par un, y compris les non tenus.

## 4. Ce que ce lot ne fait pas

- Il ne réécrit pas l'ergonomie de l'éditeur. Aucune refonte de la scène, de la pellicule ou du
  panneau de zones.
- Il ne touche pas à `checkpoints.FORMAT_VERSION`, ni au découpage de la bande dans le cache.
- Il ne crée pas d'éditeur light novel.
- Il n'ajoute aucun geste d'édition nouveau (pas de nouvel outil de zone, pas de nouveau mode de
  relettrage).
- Il ne remplace pas le verrou par une file d'attente.
- Il ne déplace ni `Services`, ni `FilDeTravail`, ni `FilDeLecture` hors de la fenêtre.
