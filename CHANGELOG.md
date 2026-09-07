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

## [2.35.2] - 2026-09-07

### CORRECTIF — un test vert parce que Windows parle français

> `config.yaml` ne change pas d'un octet. Aucun cache invalidé, `FORMAT_VERSION` reste à **3**.

#### Le défaut, et il est double

`illustration/juge.py:Encodeur.encoder` commençait par un `stat()` sur l'**image**. Avec un
encodeur absent, le message rendu était donc :

```
image illisible : …\peu importe ([WinError 2] Le fichier spécifié est introuvable)
```

— la mauvaise cause et le mauvais remède : ce qui manque est le **modèle**, et c'est lui qu'il
faut déposer. `_ouvrir()` savait le dire (« encodeur du juge introuvable : … »), mais n'était
atteint qu'après.

Le test censé garder cette propriété s'appelle
`test_l_encodeur_absent_le_dit_avant_de_mesurer` et cherchait le mot **« introuvable »**. Il
passait — mais sur le mot du **message d'erreur de Windows en français**, pas sur celui du
dépôt. La propriété annoncée par son nom n'était donc **pas tenue du tout**, et l'accident de
langue le cachait.

Sur un runner de langue anglaise, le même code rend *« The system cannot find the file
specified »* : le test échouait en intégration continue **et nulle part ailleurs**. Il est
resté invisible jusqu'à la première publication sur un dépôt public, où la CI a tourné pour de
bon.

#### Ce qui est corrigé

- le refus du modèle absent devient `_exiger_encodeur()`, appelée par `_ouvrir()` **et** en
  tête de `encoder()`. Elle ne charge rien — un `is_file()` —, de sorte qu'un succès de cache
  ne paie pas l'ouverture du modèle ;
- le test vérifie désormais **le texte que le dépôt écrit**, jamais celui que le système
  traduit. ⚠ Vérifié en retirant le correctif : il devient rouge ;
- un **garde-fou de la leçon** : un test refuse qu'un `match=` de ce fichier attende un mot
  absent de `illustration/juge.py`. Un motif qui viserait de nouveau un message de l'OS serait
  vert en français et rouge en anglais — exactement le piège qu'on vient de payer.

⚠ **Une affirmation de test a été corrigée en cours de route**, et elle mérite d'être notée :
le second test ajouté ici prétendait d'abord garder l'ORDRE des deux contrôles. Vérification
faite en retirant le correctif, il reste vert — avec une image lisible, les deux ordres
aboutissent au même message. Sa docstring dit maintenant ce qu'il garde réellement. Un test qui
surpromet est précisément le défaut que ce lot corrige ; le reproduire dans le correctif aurait
été le comble.

#### Ce que cette séquence dit de la vérification

Cinq combinaisons ont été exécutées avant de trouver — arbre de travail et arbre publié,
dépendances complètes et dépendances d'intégration, clone en LF, `--cov` — **et toutes étaient
vertes**. Ce qui manquait n'était reproductible sur aucune d'elles : il fallait une machine
dont la langue n'est pas le français. Le journal de la CI, lu par le mainteneur, a donné la
réponse en une ligne.

#### Fichiers

`illustration/juge.py` · `tests/test_illustration_juge.py`.

**Tests** : +2 — 5 036 → **5 038** collectés avec PySide6, 4 593 → **4 595** sans.

---

## [2.35.1] - 2026-09-07

### CORRECTIF — la publication a montré ce qu'aucun test local ne pouvait montrer

> `config.yaml` ne change pas d'un octet. Aucun cache invalidé, `FORMAT_VERSION` reste à **3**.
> Aucun changement de comportement de l'application : ce lot répare la **fabrication** et deux
> tests qui mesuraient l'environnement au lieu du code.

Les trois défauts ci-dessous ont ceci de commun qu'ils n'apparaissent **ni en local, ni dans
l'arbre publié** : il fallait une vraie publication et un vrai runner pour les faire sortir.

#### 1. ⚠ Le job qui attache l'installeur à la release ne partait JAMAIS

`ci.yml` déclarait `on: push: branches: ['**']`. Cela ne couvre **que les branches** : un
`git push <remote> v2.35.0` ne déclenchait pas ce workflow, et la condition
`startsWith(github.ref, 'refs/tags/')` du job `artefact` ne pouvait donc jamais être vraie sur
un événement `push`. Le job n'était atteignable que par `workflow_dispatch`.

**Conséquence, constatée le 2026-09-07 sur le dépôt public** : le tag a bien créé une release —
`publication.yml`, lui, écoute `tags: ['v*']` — mais elle est arrivée **sans aucun fichier**.
C'est exactement le manque que le lot 40 croyait avoir fermé : attacher un installeur depuis un
job qui ne part jamais ne ferme rien.

Le workflow écoute désormais `tags: ['v*']`. ⚠ Le test qui garde la correction **lit le YAML**,
pas le texte : `tags:` apparaît aussi dans les commentaires, et un garde-fou qui se contenterait
de le chercher passerait au vert sur une explication.

#### 2. La collecte des tests s'interrompait sur tout environnement sans PDF

`tests/test_completer_police.py` importait `fontTools` **au niveau module**, sans garde. Or
`fontTools` n'est déclaré dans aucun fichier de dépendances : il arrive **transitivement** par
`weasyprint`, qui est optionnel.

Un environnement socle + interface + dev — celui de l'intégration continue — n'a donc pas
`fontTools`, et cet import y faisait échouer la **collecte**, donc toute la suite, sur les deux
plateformes : *« 4 skipped, 35 deselected, 1 error »* là où la suite en compte plus de cinq
mille. Un test qui ne peut pas tourner doit s'ignorer, pas emporter ses voisins.

`pytest.importorskip` avant l'import, comme PySide6 et onnxruntime ailleurs dans ce dépôt.

#### 3. Un test dont le verdict dépendait de ce qui traînait dans l'environnement

`test_le_remede_du_cbr_vient_du_catalogue_de_reparations` vérifie que le motif d'un `.cbr`
illisible **lit son remède dans le catalogue** au lieu de le réécrire. Mais la chaîne `.cbr` a
**deux maillons** — le paquet Python `rarfile` et l'outil externe `unrar` —, et `outil_rar`
rend le premier motif venu : sans `rarfile`, elle sort avant d'avoir regardé l'outil externe.

Le test passait donc sur une machine de développement (où `rarfile` est installé) et échouait
en intégration continue, qui n'installe pas `requirements-manga.txt`. Il **pose** désormais
`rarfile` au lieu de le supposer, et le second maillon gagne **son propre test** plutôt que
d'être le hasard du premier.

#### Ce que ce lot dit de la méthode

Trois lots successifs ont livré, testé et mesuré un mécanisme de release. Il ne marchait pas.
La suite était verte à chaque fois — y compris dans un arbre de travail propre, sans corpus,
reproduisant les conditions d'un utilisateur public. Ce qui manquait n'était pas un test :
c'était **d'exécuter la chose pour de vrai**.

#### Fichiers

`.github/workflows/ci.yml` · `tests/test_completer_police.py`, `tests/test_depot_guide.py`,
`tests/test_empaquetage.py`.

**Tests** : +2 — 5 034 → **5 036** collectés avec PySide6, 4 591 → **4 593** sans.

---

## [2.35.0] - 2026-09-07

### MINEUR — trois gestes qui existaient sans être atteignables

> **Rien n'est périmé, et `config.yaml` ne change pas d'un octet.** Aucun cache invalidé,
> `manga/checkpoints.py:FORMAT_VERSION` reste à **3**.

Les trois défauts de ce lot ont la même forme, et elle mérite d'être nommée : **une capacité
livrée, testée, et inatteignable depuis l'écran**. Aucun n'aurait été trouvé par les tests du
module correspondant — ils étaient tous les trois verts.

#### 1. Le bouton « Diagnostic » du pane ne faisait rien

`gui/navigation.py:_sur_pied` n'émettait que pour les entrées portant une `action`. Or le pied
en porte **deux sortes** : « Réglages » a une action (elle ouvre un dialogue), « Diagnostic »
n'en a pas — c'est une **page** depuis le lot 36, et `destinations.pages()` le dit
explicitement (« le pied sans `action` »).

Résultat : cliquer sur Diagnostic dans le pane **ne produisait rien, en silence**. Un clic qui
ne produit rien passe pour une application cassée — c'est le reproche que `gui/depot.py` fait
déjà au lâcher muet, et il valait ici mot pour mot.

⚠ Le test qui garde la correction **échoue sans elle** (vérifié en rétablissant l'ancien
comportement), et il est doublé d'un test qui refuse de valider si un jour les deux entrées du
pied portaient une action — auquel cas il passerait au vert sans rien prouver.

#### 2. « Importer un tome corrigé » était inatteignable depuis la page Œuvres

Le geste est livré depuis la 2.34.0, mais **uniquement dans le menu « Projet »** et
**uniquement pour le tome déjà ouvert**. C'est-à-dire nulle part pour qui gère ses œuvres
depuis la page Œuvres — qui est pourtant l'endroit où l'on choisit un tome.

- la page gagne un bouton **« Importer un tome corrigé… »**, à côté de « Retoucher », avec la
  **même garde** : manga et webtoon seulement, parce que l'import réintègre des checkpoints de
  planches et qu'un roman n'a rien à en faire ;
- le signal porte **le projet ET le tome** (`demande_import = Signal(str, str)`). Un signal sans
  argument aurait obligé à repasser par le tome courant, donc aurait reconduit exactement le
  défaut ;
- `Fenetre.action_importer_build` accepte désormais un tome explicite et retombe sur le tome
  ouvert quand on ne lui en donne pas — le menu et la page marchent tous les deux, sans que
  l'un impose son chemin à l'autre.

#### 3. « Vérification impossible : aucune version n'est publiée »

La phrase se contredisait : la vérification a parfaitement abouti, c'est la **réponse** qui est
« il n'y en a pas ». Et c'est le **cas nominal** d'un dépôt public tant qu'aucun tag n'y a été
poussé — donc la première phrase que tout le monde lit.

Elle devient : « Aucune version n'est encore publiée sur le dépôt — vous avez la dernière
disponible », avec l'adresse de la page. ⚠ Un vrai échec réseau continue de dire « impossible » :
un test iso l'exige, pour que la correction n'avale pas les échecs qui en sont vraiment.

#### ⚠ Ce que ce lot ne corrige PAS, et qui n'est pas un défaut de code

L'exécutable gelé ne proposait pas « Rechercher une mise à jour » parce qu'il **datait de la
2.31.0** : la fonction est arrivée en 2.34.0. Les binaires sont regénérés ici.

Et la vérification de mise à jour ne trouve rien parce que le dépôt public **ne porte aucune
release** — mesuré le 2026-09-07 : l'API rend `200` sur le dépôt (il est bien public) et une
liste **vide** sur `/releases`. Le mécanisme qui produit une release existe et est complet
(`ci.yml`, job `artefact`, sur tag `v*`) ; il n'a simplement jamais été déclenché, faute de tag
poussé sur le dépôt public. Ce n'est pas un correctif à écrire, c'est un geste de publication.

#### 4. ⚠ Le gel réussissait ou échouait selon l'endroit où l'on avait cliqué

Trouvé en regénérant les binaires, par la vérification du gel elle-même. La troisième
vérification affirme que *« la fenêtre s'ouvre sur l'accueil »*. Or l'application rouvre la
dernière destination visitée, et une installation gelée lit `.angelith/interface.json` dans
`%LOCALAPPDATA%\Angelith` — c'est-à-dire **le profil réel de qui vient de se servir de
l'application**.

Une session laissée sur la page Diagnostic a donc fait échouer une compilation dont le code
était sain. En intégration continue le profil est vide, le piège n'y apparaît jamais : c'est un
garde-fou qui ne dit la vérité que sur une machine neuve.

`tools/geler.py` isole désormais les réglages dans un dossier temporaire, par
`ANGELITH_REGLAGES` — la variable existe précisément pour ça. La vérification mesure enfin ce
qu'elle prétend mesurer : l'état d'un **premier lancement**.

#### 5. Le manifeste d'empreintes listait des versions qui n'existaient plus

Même famille, trouvée dans la foulée : `SHA256SUMS.txt` est écrit en balayant `dist/`, donc un
installeur d'une version précédente resté là s'y retrouvait. Le fichier annonçait deux versions
dont une seule existait encore.

⚠ Ce n'est pas cosmétique. `ci.yml` attache `dist/*.exe` à la release, et `core/maj.py` retient
le **premier** asset qui finit par `-setup.exe` : une release portant deux installeurs ferait
télécharger l'un ou l'autre selon l'ordre rendu par l'API. `tools/geler.py` retire désormais de
`dist/` les installeurs d'une autre version que celle qu'il vient de geler — **et rien d'autre**,
ce qu'un test vérifie en posant un fichier voisin qu'il ne faut pas toucher.

#### Fichiers

`gui/navigation.py`, `gui/oeuvres.py`, `gui/fenetre.py`, `core/maj.py`, `tools/geler.py` ·
`tests/test_gui_navigation.py`, `tests/test_gui_vue_oeuvres.py`, `tests/test_core_maj.py`.

**Tests** : +9 — 5 025 → **5 034** collectés avec PySide6, 4 585 → **4 591** sans.

---

## [2.34.0] - 2026-09-06

### MINEUR — créer un light novel, réintégrer un tome corrigé, et se mettre à jour

> **Rien n'est périmé, et il n'y a rien à réarmer.** `config.yaml` change d'une seule valeur —
> `maj.verifier` passe de `false` à **`true`** —, empreinte SHA-256 (fins de ligne LF, telles
> que git les stocke) `f61e9c864991…` → `62da35fab412…`. Aucun cache invalidé,
> `manga/checkpoints.py:FORMAT_VERSION` reste à **3**.

#### 1. « Light novel » existe enfin dans la boîte de création

C'était le manque le plus étrange du lot 31 : la boîte proposait Manga et Webtoon, mais **pas
la brique historique du projet**. Ce n'était pas un oubli d'interface —
`manga/creation_projet.py` était le **seul module du dépôt qui écrive sous `sources/`**, et il
ne connaissait que deux formats. Aucune fonction ne savait créer
`sources/<Projet>/<Tome>/<LANGUE>/` ; `app.py` disait à l'utilisateur de faire le dossier à la
main.

- **`creation.py`** (racine, comme `bibliotheque.py`) porte les **trois dispositions**. Le light
  novel n'a **pas** de cran `<format>` : `pipeline/sources.py:_langues_presentes` fait un
  `iterdir()` sur le dossier du tome, et insérer un `light_novel/` rendrait le tome invisible au
  pipeline qui doit le lire ;
- la **langue est obligatoire** pour un roman, et refusée à la création plutôt qu'après : un
  tome sans dossier de langue n'est lisible par personne ;
- **`manga/creation_projet.py` reste** et continue de marcher — un test l'exige ;
- **glisser-déposer** : `.pdf` et `.epub` proposent un projet light novel. ⚠ `.docx`, `.txt` et
  `.md` restent des glossaires : l'extension seule ne dit pas si le fichier est un glossaire
  rédigé à la main ou un tome, et le dépôt refuse de deviner.

> **La preuve qui compte** n'est pas une assertion sur des noms de dossiers : un tome est créé
> **par langue**, et c'est le détecteur de `pipeline/sources.py` qui doit le voir. Un dossier
> créé que le pipeline ignorerait serait pire qu'une absence de fonction.

⚠ **Un test existant est devenu dangereux, pas seulement faux.**
`test_un_lacher_inconnu_produit_un_message_pas_un_silence` employait un `.pdf` comme exemple
d'inconnu ; le lot en fait un roman, donc le lâcher ouvrait une **boîte modale** et la suite
entière se figeait **sans une ligne de sortie**. Le test est réécrit (exemple `.psd`, propriété
inchangée) et doublé d'un test neuf sur le comportement voulu.

#### 2. Importer un `build/` corrigé par un tiers

Donner un tome à relire et récupérer le travail : `import_build.py` (racine, sans Qt) compare le
`projet.json` reçu au local et rend un **plan** avant d'écrire quoi que ce soit.

- **trois refus, avant toute écriture** : un autre tome, un `regions.json` d'une autre version
  de format, un run en cours ;
- **rien n'est supprimé**, jamais : une planche présente ici et absente du paquet est conservée ;
- ce qui est **écrasé** part d'abord dans `.avant-import-<date>/`.

> ⚠ **Le refus de version est celui qui compte, et il ne passe PAS par
> `checkpoints.checkpoint_format`.** Cette fonction exige `regions.json` **et** `masks.png` : un
> paquet sans masques lui aurait fait rendre `None`, et le garde-fou aurait été **contourné en
> silence**. Or l'ordre persisté dans `regions.json` est le pivot auquel `ocr.json` et
> `traduction.json` s'alignent **par position** — un cache d'une autre version ferait atterrir
> les traductions dans les mauvaises bulles, sans un message.

**Mesuré sur les 10 tomes manga du corpus** (16,54 Go, 14 973 fichiers) : les `.checkpoints/` —
c'est-à-dire **tout le travail humain** — pèsent **0,1 % du poids** et représentent **72 % des
fichiers**. D'où la case « importer aussi les planches rendues », **décochée** : transférer 3 Go
pour 4 Mo de corrections doit être un choix explicite.

#### ⚠ Trois défauts trouvés, et tous les trois dans le CÂBLAGE

`creation.py`, `import_build.py` et `gui/vue_maj.py` étaient verts avec 56 tests sans écran
pendant que l'interface, elle, était cassée à trois endroits. C'est l'argument pour les
13 tests **montés** que ce lot ajoute, après quatre lots qui n'en ajoutaient aucun.

1. **la boîte d'import ne s'activait jamais** — `_relire` appelait `theme.poser_role(…, "")`,
   or `poser_role` refuse un rôle inconnu par un `KeyError`. L'exception coupait la méthode : la
   liste des planches restait vide et le bouton « Importer » restait gris ;
2. **la boîte de création s'ouvrait sans langues** — la liste dépend désormais de la
   disposition et se recalcule sur `currentTextChanged`, **qui ne part pas à la construction**.
   Un manga se créait donc sans langue par accident, et un roman pas du tout. ⚠ Le test qui l'a
   trouvé **interroge** le combo au lieu de le cliquer : un test qui aurait simulé un changement
   de format aurait déclenché le signal manquant et serait passé au vert sur un défaut intact ;
3. **rafraîchir la liste des modèles rouvrait la fenêtre de mise à jour** — la réception
   retombait sur le résultat du dernier clic quand la tâche courante n'en portait pas, et
   « Rafraîchir la liste » est une tâche du même genre. Une tâche répond de **son** résultat.

#### 3. La mise à jour — et l'affirmation du lot 37 est LEVÉE, pas effacée

> **`maj.verifier` passe à `true`.** L'affirmation « désarmé par défaut, et le motif est un
> différenciateur du produit » est levée par un **bloc daté** dans `core/maj.py` et dans
> `config.yaml`. Elle n'est pas fausse : elle décrit ce que la 2.31.0 livrait. Mais
> « 100 % local, rien ne sort de la machine » porte sur les **œuvres** — aucun texte, aucune
> planche, aucun glossaire, aucune traduction ne quitte cette machine, et cela **reste vrai mot
> pour mot**. La formulation de 2.31.0 mettait les deux dans le même sac.
>
> ⚠ **La clé absente vaut toujours `false`** : une installation antérieure au lot 37 n'a pas la
> section `maj:` et ne se met pas à appeler le réseau parce que personne ne lui a rien dit. Et
> `verifier: false` continue de garantir qu'aucun octet ne part — c'est toujours testé avec un
> `httpx` dont le `get` lève.

- **le prérequis, que rien ne remplissait** : `ci.yml` attache maintenant l'installeur **et**
  `SHA256SUMS.txt` à la release. `publication.yml` créait une release **sans aucun fichier**, et
  le job `artefact` téléversait des artefacts de *workflow*, qui n'en sont pas — un updater
  n'aurait eu **rien à télécharger** ;
- **le bouton** « Aide › Rechercher une mise à jour… » télécharge, **vérifie l'empreinte
  SHA-256** contre le `SHA256SUMS.txt` de la même release, demande une dernière confirmation,
  lance l'installeur et quitte ;
- ⚠ **ce que l'empreinte NE protège PAS est écrit à l'écran** : elle détecte un téléchargement
  tronqué ou altéré en transit, elle ne remplace **pas** une signature de code — aucun
  certificat ne signe ces binaires, et le fichier d'empreintes vient de la même main que
  l'exécutable ;
- **hors gel**, rien ne s'installe : on ne remplace pas l'arbre de travail de quelqu'un qui a
  cloné le dépôt. Le bouton ouvre la page des releases, et `core.maj.installer` refuse au même
  endroit ;
- **sans `SHA256SUMS.txt` dans la release, on ne télécharge même pas** : un installeur qu'on ne
  peut pas vérifier vaut moins qu'un lien, parce qu'il aurait l'air vérifié ;
- **le contrôle au démarrage part dans le fil de travail**, avec les trois sondes de l'accueil,
  jamais sur le fil d'affichage ;
- **« Ne plus afficher »** écrit `maj_silencieuse` dans `.angelith/interface.json`. ⚠ Il masque
  **la fenêtre**, pas la capacité — le bouton continue de marcher, la fenêtre le dit, et la case
  se décoche depuis Préférences › Au démarrage.

**Mesuré le 2026-09-06** : l'installeur pèse **292,1 Mio** ; son SHA-256 se calcule en
**0,27 s** (1 062 Mio/s) ; un débit de **2,5 Mio/s** relevé sur un asset de release GitHub
public (1 mesure, 2,0 Mio lus) donnerait **~115 s**. La vérification est gratuite devant le
téléchargement — et ~115 s, c'est ce qui impose la barre de progression et le fil de travail.

> ⚠ **CE QUI N'EST PAS TENU** : aucun aller-retour réel n'a pu être mesuré. `GET` sur l'API du
> miroir rend **404 en 0,72 s** — le dépôt public est privé jusqu'à la candidature NLnet et
> aucune release n'y existe. Le chemin « télécharger → vérifier → installer » est écrit et testé
> **contre des doubles**. C'est une limite nommée de ce lot, détaillée dans
> `docs/mesures/creation-import-maj-2026-09-06.md` §4.2.
>
> Ce 404 a d'ailleurs **changé la conception** : `verifier()` le traite comme une **absence** et
> non comme une erreur, et la fenêtre ne s'ouvre **jamais** sur un échec de vérification — sinon
> ce lot aurait livré une fenêtre d'erreur quotidienne à tout le monde.

#### Fichiers

`creation.py`, `import_build.py`, `gui/vue_maj.py` (neufs) · `core/maj.py`, `config.yaml`,
`gui/dialogues.py`, `gui/fenetre.py`, `gui/depot.py`, `gui/actions.py`, `gui/reglages.py`,
`gui/travailleur.py`, `.github/workflows/ci.yml` · `tests/test_creation.py`,
`tests/test_import_build.py`, `tests/test_gui_vue_maj.py`, `tests/test_gui_dialogues_maj.py`
(neufs) · `tests/test_core_maj.py`, `tests/test_gui_depot.py`, `tests/test_gui_fenetre.py` ·
`docs/mesures/creation-import-maj-2026-09-06.md`.

**Tests** : +113 — 4 912 → **5 025** collectés avec PySide6, 4 496 → **4 585** sans. L'écart
passe de 416 à **440** : ce lot est le premier depuis le 36 à ajouter des tests qui exigent un
écran, et c'est délibéré — les trois défauts qu'il a trouvés n'étaient trouvables que montés.

---

## [2.33.0] - 2026-09-06

### MINEUR — Angelith tourne sans serveur LLM : bulles vides, saisie manuelle, et le diagnostic cesse de dire que rien n'est utilisable

> **Rien n'est périmé, et il n'y a rien à réarmer.** `config.yaml` change d'une seule chose —
> une clé `llm.actif`, **armée** (`true`) —, empreinte SHA-256 `f879ce66ff58…` →
> `04c4d0278ccb…`. Aucun cache invalidé, `manga/checkpoints.py:FORMAT_VERSION` reste à **3**, et
> la sortie console de `run.py --check` et `run_manga.py --check` est **inchangée octet pour
> octet**.

#### Le besoin, et ce qui l'empêchait

Toutes les machines ne peuvent pas faire tourner un LLM en local. Or un endpoint injoignable ne
dégradait pas Angelith, il l'arrêtait : la page Diagnostic annonçait « **Aucune brique n'est
utilisable en l'état** » à quelqu'un dont le nettoyage, l'OCR, le relettrage et la saisie
manuelle marchaient parfaitement — `gui/lanceur.py` décrit pourtant `--from rendu` comme
« relettrage seul, **aucun appel LLM** ».

#### ⚠ La mesure de l'étape 0 a changé la conception

La question posée était : « le lettrage plante-t-il sur un tome sans `traduction.json` ? »
Réponse : non, `typeset_page` complète avec des chaînes vides. Mais la mesure a trouvé pire :

```
traduction.json ABSENT             ->  0 correction(s) appliquée(s) sur 3, sortie = []
traduction.json de 3 chaînes vides ->  3 correction(s) appliquée(s) sur 3
```

`checkpoints.appliquer_manuelles(None, …)` part d'une liste **vide**, et son garde
`0 <= index < len(sortie)` rejette alors **tout**. Un mode qui se serait contenté de *sauter*
la traduction aurait donc fait perdre **silencieusement chaque réplique saisie dans la
Retouche** — c'est-à-dire exactement le geste qu'il existe pour servir.

⚠ Ce n'est pas un défaut de `appliquer_manuelles` : son refus est délibéré et documenté (« on
préfère perdre la correction que décaler la planche »). D'où la décision : **le mode ÉCRIT un
`traduction.json` d'une chaîne vide par bulle**, il ne l'omet pas. La saisie atterrit au bon
index, le rapport ne porte aucun `ecart_comptage`, et le graphe d'étapes reste cohérent.

#### Trois portes, un seul état

- **`llm.actif: false`** dans `config.yaml` — le niveau **installation**, pour une machine qui
  ne fera jamais tourner de LLM. Héritage profond : `manga.llm.actif` l'emporte, ce qui permet
  de désarmer le manga sans toucher au light novel. Même nom et même doctrine que
  `illustration.llm.actif`, qui existait déjà ;
- **`--sans-llm`** sur `run.py` et `run_manga.py` — deuxième fragment réellement partagé de
  `core/cli.py` après `ajouter_flags_veille`, et pour le même critère écrit : même nom, même
  sémantique, même aide ;
- **une case** dans les formulaires manga et webtoon, à **trois états** (`None` = « selon
  `config.yaml` »). Elle ne peut qu'**armer** : ne pas la cocher ne réarme pas la traduction
  d'une machine dont le fichier l'a désarmée.

⚠ **Ce n'est PAS `--dry-run`.** Celui-ci SIMULE une traduction — le texte source traverse
l'agent inchangé et s'écrit comme s'il était traduit. Ici rien ne prétend avoir traduit : le
`RAPPORT.md` porte un bandeau **« MODE SANS LLM »** en tête de section, avec le nombre de bulles
laissées vides et où les saisir.

#### ⚠ Le light novel REFUSE ce mode, et le dit

`run.py --sans-llm` accepte le drapeau et **s'arrête**, en expliquant et en donnant la commande
de rechange. Il n'existe aucune surface de saisie manuelle pour de la prose — la Retouche est un
éditeur de PLANCHES — et un roman rendu sans traduction sortirait avec **son texte source dans
un `.docx` français**, c'est-à-dire une sortie fausse. `pipeline/orchestrator.py` le dit déjà
d'un traducteur désactivé : « sans traduction, le pipeline n'a rien à produire ».

Le drapeau existe quand même sur cette CLI : l'omettre ferait croire à un oubli et renverrait un
`unrecognized arguments` qui n'explique rien. **C'est une limite nommée du lot, pas un oubli** —
l'ouvrir demanderait un éditeur de prose.

#### Le LLM devient une CAPACITÉ, plus une brique

`serveur_llm` passe de la brique `socle` à `diag.LLM`. Comme `DEPENDANCES_BRIQUE` met `SOCLE`
dans les quatre briques, le classer là le faisait bloquer les quatre. Il est désormais dans la
portée de `ln` et `manga` — donc **rien ne change pour un run qui traduit** — et
`bloquants_pour(..., sans_llm=True)` sait l'en retirer. La page dit maintenant ce qui reste :

> Sans traduction, **manga et webtoon reste utilisable** : nettoyage, OCR, relettrage et saisie
> manuelle n'appellent aucun modèle de langue.

⚠ Le **texte console est inchangé** : `brique` n'est pas imprimé. `SCAN` et `ILLUSTRATION` ne
dépendent pas du LLM, et ce n'est pas un oubli — la brique scan lit des pages sans traduire.

#### Le filet qui évite de perdre des heures de GPU

`_passe_terminologie` tournait **hors du filet par planche**, entre le balayage A (détection →
nettoyage → OCR) et le balayage C. Une `RuntimeError` du client LLM y **tuait le tome entier**,
après que la détection et l'OCR de 150 planches avaient déjà tourné. Elle passe sous
`_passe_terminologie_protegee` : `StopRequested`, `KeyboardInterrupt` et `SystemExit` la
traversent comme dans `_filet` ; le reste est capté, **nommé** dans les stats et le rapport, et
le tome continue avec le glossaire du disque.

#### Le serveur LLM se règle depuis l'interface

`core/modeles.outrepasser_endpoint` — même patron que `outrepasser` : mute la configuration
**déjà chargée**, rend `(avant, après)`, et **n'écrit jamais `config.yaml`** (interdit 5). Le
champ vit dans les Préférences avec un bouton « Tester », persisté sous `serveur_llm` dans
`.angelith/interface.json`, `None` = « s'en remettre à `config.yaml` ». ⚠ Une adresse vide ne
coupe rien — c'est la règle des trois états.

#### Corrigé en passant

**`gui/sondes.py:url_llm` lisait TOUJOURS `config["llm"]` racine** et ignorait un
`manga.llm.base_url` distinct — alors que `manga/doctor.py` le respecte, lui. Sur une
installation qui pointe la brique manga vers une seconde machine, l'accueil et le sélecteur de
modèles **sondaient le serveur du light novel**. Le paramètre `section` est additif : sans lui,
le comportement est identique au bit près.

**Un test existant a été RÉÉCRIT, pas assoupli.** `test_la_section_ollama_rend_un_verdict_
bloquant_du_socle` affirmait que « le serveur LLM appartient au SOCLE : son absence bloque
toutes les briques, et c'est la seule famille de verdicts dont ce soit vrai », et il le
vérifiait fidèlement — c'est précisément ce qui rendait le défaut invisible.

**Un garde-fou du dépôt a fait son travail.** `tools/inventaire_drapeaux.py` a refusé la
livraison tant que `ajouter_flag_sans_llm` n'était pas déclaré comme second helper : le drapeau
est posé depuis `core/cli.py`, donc invisible à un `grep add_argument run_manga.py`. C'est
exactement l'écart que cet outil existe pour supprimer.

#### Ce que ce lot ne fait pas

⚠ **Un critère n'est pas tenu, et il est écrit** : le récapitulatif de lancement ne dit
toujours pas l'état de l'endpoint. Le faire demande une sonde réseau au moment du clic, donc sur
le fil d'affichage — ce que `gui/sondes.py` interdit en toutes lettres, avec un motif mesuré
(12,1 s de fenêtre gelée). Le faire proprement suppose de passer par le fil de travail et de
rendre le dialogue asynchrone.

⚠ **Et le manque principal : aucun run réel n'a tourné en mode sans LLM.** Le chemin est complet
et testé pièce par pièce ; l'usage ne l'est pas. La boucle de traduction du light novel reste
sans filet (un trou dans un chapitre est pire qu'un run qui s'arrête), `core/llm.py` lève
toujours après trois tentatives, et **aucune bascule automatique** n'est livrée — produire
silencieusement un tome vide parce qu'un serveur était arrêté serait exactement ce que ce dépôt
refuse.

**Tests** : +26, **tous sans Qt** — 4 886 → **4 912** collectés avec PySide6, 4 470 → **4 496**
sans, l'écart de **416** inchangé et mesuré des deux côtés. Tout est dans
`docs/mesures/sans-llm-2026-09-06.md`, qui reprend les quinze critères un par un, dont celui qui
n'est pas tenu.

## [2.32.0] - 2026-09-06

### MINEUR — Compiler tient en une commande, et le dépôt cesse de dire trois choses sur la même licence

> **Rien n'est périmé, et il n'y a rien à réarmer.** `config.yaml` ne change pas d'une ligne —
> empreinte SHA-256 `f879ce66ff58…`, **inchangée**. Aucun cache, aucun checkpoint, aucun prompt,
> aucun seuil, aucun format de sortie, aucune clé de configuration.
> `manga/checkpoints.py:FORMAT_VERSION` reste à **3**, et la sortie console de `run.py --check`
> et `run_manga.py --check` est **inchangée octet pour octet**.

#### Le défaut principal : trois licences pour le même fichier, dont une fausse

Le dépôt disait **trois choses différentes** du détecteur de bulles, et ces phrases sont
**affichées** à quelqu'un qui s'apprête à télécharger un fichier sous une licence qui n'est pas
celle du projet :

| Source | Ce qu'elle disait |
|---|---|
| `manga_models/README.md` | GPL-3.0, déclarée sur la page du modèle (relevé le 2026-08-25) |
| `manga/reparations.py` | AGPL-3.0 (export YOLOv8-seg ; Ultralytics YOLOv8 est AGPL-3.0) |
| `gui/sondes.py`, `manga/doctor.py` | **GPL-3.0 + Manga109-s** ⚠ **faux** |

Manga109-s concerne le détecteur de **texte sur le dessin** (`mayocream/comic-text-detector`),
pas celui des bulles (`kitsumed/yolov8m_seg-speech-bubble`) — `manga/models.py` le disait déjà
sans ambiguïté. Les deux premières lignes, elles, ne se contredisent pas : la page du modèle
*déclare* GPL-3.0, et les poids *sont* un export YOLOv8-seg dont l'amont est AGPL-3.0. **Les
deux faits comptent pour qui rediffuse**, et le lot les écrit tous les deux plutôt que
d'arbitrer en silence.

**`manga/models.py` devient la source unique** — licence, URL de licence, note, avec leur date
de relevé. Les quatre modules qui affichaient une licence la **lisent** désormais.
`tests/test_licences_poids.py` refuse qu'elle soit réécrite, et que « Manga109 » réapparaisse à
côté du détecteur de bulles.

#### La licence n'atteignait jamais le corps de la page

`gui/vue_diagnostic.phrase_geste()` rendait `verdict.geste` **en priorité**, et tous les
verdicts réparables des doctors en portent un : la branche qui appelait `reparation.consigne()`
— la seule qui écrive la licence — **n'était jamais atteinte**. Elle n'existait à l'écran qu'en
infobulle du bouton et dans la boîte de confirmation, c'est-à-dire **après** le clic. Pire, le
geste de `poids_detection` **promettait** « licence affichée avant » sans jamais la nommer.

`phrase_licence()` s'ajoute à côté du geste — le geste dit quoi faire, la licence dit sous
quelles conditions.

#### Deux réparations sur quatre étaient inatteignables

`poids_texte` et `modele_ocr` sont déclarées `RECUPERABLE`, avec leur URL, leur taille, leur
empreinte et leur geste — et **aucun verdict ne les nommait**. Comme `bouton_pour()` exige un
`Verdict`, rien, nulle part, ne pouvait les déclencher depuis l'interface.

⚠ **La correction n'est pas d'ajouter deux verdicts** : la sortie console est un contrat
scripté, et surtout **télécharger un poids est un geste, pas une réparation d'erreur**. La page
Diagnostic gagne un bloc **« Poids et modèles »** permanent — les quatre, avec leur licence,
leur taille, leur état et un bouton chacun, **visible sans qu'aucun diagnostic ait tourné**.

L'état n'est affiché que lorsqu'il est mesurable : `modele_ocr` vit dans le cache de
`huggingface_hub` et `polices` dans le registre de Windows, deux endroits dont ce projet n'est
pas propriétaire. La page dit « état non mesuré » et **garde le bouton** — récupérer un modèle
déjà présent est idempotent, alors que masquer le bouton laisserait sans recours quelqu'un dont
le cache est corrompu.

#### Compiler — de cinq commandes à une

**`tools/geler.py`** (neuf) enchaîne : l'outillage, la régénération de `installeur/version.iss`
depuis `core/version.py`, le gel en un dossier, les **trois vérifications** du binaire,
l'installeur, les empreintes SHA-256. `docs/COMMANDES.fr.md` en listait cinq à recopier dans le
bon ordre, et le coût s'est vu au lot précédent : **l'installeur mesuré du lot 37 porte
2.30.0** alors que le dépôt était en 2.31.0, faute d'avoir régénéré le fichier de version avant
de compiler. L'outil régénère **avant** de geler.

⚠ **Sa première exécution a trouvé un défaut réel** : `ci.yml` cherchait Inno Setup uniquement
dans `C:\Program Files (x86)\Inno Setup 6\`, or une installation par `winget --scope user` — la
machine principale du projet — le met dans `%LOCALAPPDATA%\Programs\`. Le job de CI aurait
marché, **la commande documentée non**. L'outil cherche dans le `PATH` puis aux trois
emplacements connus, et **la CI l'appelle** : les deux chemins sont désormais identiques par
construction.

Il **n'installe rien** — ni PyInstaller, ni Inno Setup. `pyinstaller` n'est déclaré dans aucun
`requirements-*.txt` et c'est délibéré : un empaqueteur n'est pas une dépendance de ce qu'il
empaquette. Un test refuse tout appel de sous-processus à un gestionnaire de paquets.

#### La sonde `.cbr` rebranchée — le seul report que la série 31-37 avait laissé ouvert

`docs/mesures/bibliotheque-2026-09-05.md` écrivait que la sonde `unrar` de `gui/depot_guide.py`
était « écrite pour être **remplacée** » par celle du `PLAN-36`. Le `PLAN-36` a été livré en
**2.30.0** ; le rebranchement, lui, n'a jamais eu lieu — le module gardait ses deux
`shutil.which`, son propre texte de remède, et son avertissement disant que le lot 36 n'était
pas livré. `outil_rar()` appelle maintenant `core.diagnostic.verdict_outil_externe()` — qui
était du **code mort**, sans appelant en production — et lit son remède dans
`core/reparations.py`.

#### Affirmations d'état levées (règle §5 bis)

`.github/workflows/publication.yml` affirmait encore « Aucun empaquetage » et « le projet n'est
pas empaqueté et ne veut pas l'être ; c'est la raison de l'absence de `pyproject.toml` » — deux
phrases que la 2.31.0 a rendues fausses sans venir les lever. Levées par un bloc daté. Ce qui
tient de la seconde est sa **conclusion** — pas de publication PyPI — avec un motif neuf.
`docs/roadmap.md` annonçait « Current released version: 2.30.0 » alors que la ligne 75 du même
fichier décrivait la 2.31.0.

⚠ **Un manque nommé, non corrigé ici** : `publication.yml` crée une release **sans aucun
fichier**, et le job `artefact` téléverse des artefacts de *workflow*, qui ne sont pas des
assets de release. Une mise à jour automatique n'aurait rien à télécharger. C'est écrit dans
l'en-tête du fichier plutôt que découvert plus tard.

#### Ce que ce lot ne fait pas

Il ne vérifie **pas** les licences à leur source — il les rend cohérentes et datées ; la
justesse reste une vérification humaine, et sa date est celle du relevé. Il ne clique sur aucun
des trois boutons neufs contre le réseau réel. Il ne signe aucun binaire. Il ne change rien pour
qui lance `python gui.py`.

**Tests** : +40, **tous collectés dans les deux configurations** — 4 846 → **4 886** avec
PySide6, 4 430 → **4 470** sans, l'écart de **416** inchangé et mesuré des deux côtés. Tout est
dans `docs/mesures/compilation-licences-2026-09-06.md`, qui reprend les douze critères du lot un
par un.

## [2.31.0] - 2026-09-06

### MINEUR — L'empaquetage : `pyproject.toml`, un dossier gelé, un installeur qui n'efface rien, un artefact que la CI teste

> **Rien n'est périmé pour qui lance `python gui.py`.** Aucun cache, aucun checkpoint, aucun
> prompt, aucun seuil, aucun format de sortie n'est touché ;
> `manga/checkpoints.py:FORMAT_VERSION` reste à **3**. `config.yaml` change d'une seule
> chose — une section `maj:` de trois clés, **désarmée** —, empreinte SHA-256
> `77cb4bf311ae…` → `f879ce66ff58…`.
>
> ⚠ **Le numéro est MINEUR et pas MAJEUR, et le plan invitait à trancher à la livraison.** Le
> lot déplace bien `config.yaml` et `.angelith/` — mais **uniquement dans une installation
> gelée**, qui n'existait pas avant lui. Pour l'utilisateur du dépôt, la règle du CHANGELOG
> ne se déclenche sur aucun de ses deux critères : il n'y a ni `build/` à supprimer, ni
> `config.yaml` à éditer avant de relancer la même commande.
>
> ⚠ **UNE chose change quand même, et le critère 5 du plan demande de la dire précisément.**
> Les cinq `requirements-*.txt` deviennent des **enveloppes** (`-e .[manga]`). Conséquences :
> `pip install -r requirements.txt` installe désormais aussi `angelith` lui-même, en mode
> éditable, et **doit être lancé depuis la racine du dépôt** — un `-e .` d'un fichier de
> requirements se résout contre le répertoire courant, pas contre le fichier. Le jeu de
> dépendances résolu, lui, est identique : les spécificateurs sont recopiés à la lettre dans
> `pyproject.toml`, plafond `openai<3` compris.

#### Ce que le lot livre

**`pyproject.toml`** (neuf) — nom public **Angelith**, licence **AGPL-3.0-or-later**, et la
version **lue** depuis `core/version.py` (`[tool.setuptools.dynamic]`), jamais recopiée.
`tests/test_pyproject.py` compare la version des métadonnées à `__version__` : deux numéros,
ce serait un `tests/test_version.py` qui passe pendant qu'on livre le mauvais.

Six points d'entrée : `angelith`, `angelith-manga`, `angelith-ocr`, `angelith-illustration`,
`angelith-console` en console, et `angelith-gui` en `gui_scripts` — pour ne pas ouvrir de
console noire sous Windows.

**`core/installation.py`** (neuf) — **la** fonction de résolution des données livrées, et la
seule du dépôt qui connaisse `sys._MEIPASS`. Trois racines qui ne se confondent pas : le
paquet (lecture seule), `%LOCALAPPDATA%\Angelith` (réglages, `config.yaml` utilisateur, poids
téléchargés) et `Documents\Angelith` (les œuvres). Hors gel, chacune de ses fonctions rend
exactement ce que le dépôt rendait avant — c'est ce que tient `tests/test_installation.py`.

**`config.yaml` dans une installation** — résolu dans l'ordre `--config` → copie utilisateur →
copie livrée. La copie se fait **une fois**, par `shutil.copy2` (donc les 158 Ko de prose
arrivent intacts), et **n'est jamais remplacée** par une mise à jour. L'écart avec le fichier
livré est **dit**, jamais fusionné : `ecart_de_config()` nomme les clés ajoutées depuis. On ne
fusionne pas un document.

**`angelith.spec`** (neuf) — un gel **en un dossier**, et le refus de `--onefile` est motivé
dans le fichier : l'extraction-puis-exécution au démarrage est le motif que les heuristiques
antivirus signalent, et elle coûterait une décompression à chaque lancement. UPX est désactivé
pour la même raison. Deux exécutables depuis la même analyse : `angelith-gui.exe` (fenêtré) et
`angelith-console.exe` — sous Windows, un binaire fenêtré n'a pas de sortie standard, et la CI
ne pourrait rien lire du gel.

**`installeur/angelith.iss`** (neuf) — Inno Setup, installation **par utilisateur**
(`PrivilegesRequired=lowest`), sans UAC, hors de `Program Files`. Sa version vient de
`core/version.py` par un fichier généré. **Sa désinstallation ne touche à aucune donnée** :
ni œuvres, ni `build/`, ni poids, ni `config.yaml` utilisateur — une seule case, dont le
bouton par défaut est « Non », propose d'effacer les réglages. Vérifié par exécution : cinq
fichiers témoins posés avant, cinq présents après.

**`core/maj.py`** (neuf) — savoir qu'une version existe, **désarmé par défaut**
(`maj.verifier: false`). Un `GET` sur les releases GitHub et une comparaison de trois entiers ;
aucun identifiant, aucune télémétrie, aucun numéro de version dans l'agent utilisateur, aucun
corps de requête. Aucune mise à jour automatique n'est livrée, et c'est un choix écrit : un
mécanisme de mise à jour est un canal d'exécution de code sur la machine de quelqu'un d'autre.

**Un job de CI `artefact`**, sur les tags — il gèle, construit l'installeur, publie les
SHA-256, et surtout **teste le gel** par `tools/verifier_gel.py` : la version survit, le
diagnostic structuré se collecte sur une machine nue, la fenêtre s'ouvre sur l'accueil sans
ouvrir de tome.

#### Ce que le lot a trouvé, et qu'aucun test du dépôt n'aurait vu

Quatre défauts, tous rencontrés sur le binaire gelé le 2026-09-06 :

- **le jeu « socle + interface » ne démarre pas** : `gui/fenetre.py` → `manga/etat_planches.py`
  → `manga/checkpoints.py` importe `numpy` au niveau du module. Un paquet sans `numpy` n'existe
  donc pas, et c'est ce qui a fixé le plancher du paquet livré ;
- **un binaire fenêtré n'écrit nulle part**, et une exception non rattrapée y ouvre une boîte
  que personne ne clique — le premier essai de vérification n'est jamais sorti ;
- **`cli.configurer_stdout()` avait été perdu** au déménagement de `main` vers
  `gui/lancement.py` : le gel est mort sur `UnicodeEncodeError` au premier « ⚠ » de sa sortie
  JSON, sur une console cp1252 ;
- **l'installation échoue dans un chemin profond** : le chemin relatif le plus long du gel fait
  **131 caractères**, tous venant des licences tierces de `torch`, ce qui ne laisse que 82
  caractères de marge sous `MAX_PATH`. ⚠ **Non corrigé par ce lot**, écrit dans le document de
  mesure.

#### La forme du produit, tranchée sur des chiffres

Quatre venv propres pesés, trois gels construits. `manga-ocr` (donc `torch`) coûte **+526,4 Mo
et +4 906 fichiers** au gel — ×2,4 en poids, ×14,8 en nombre de fichiers. Sans lui, **27 des
55 tomes** du corpus restent traitables, et **aucun manga**. Et les deux voies « on
l'installera après » sont mesurées **impossibles** : un exécutable PyInstaller n'est pas un
interpréteur, et déposer les paquets dans le gel échoue sur la bibliothèque standard élaguée
(`No module named 'timeit'`). Le paquet livré est donc **complet** : 916,5 Mo de dossier gelé,
**291,1 Mo** d'installeur.

#### Antivirus et signature — mesuré d'un côté, non mesuré de l'autre

**Windows Defender du 2026-09-06** (moteur `1.1.26080.3`, signatures `1.459.74.0` du même
jour) : **aucune menace** sur les deux dossiers gelés et sur l'installeur non signé.
⚠ **Le taux multi-moteurs n'est PAS mesuré** — soumettre un binaire à VirusTotal le publie
dans un dépôt d'échantillons consultable par des tiers, et c'est une décision de publication
qui a été posée et déclinée. On ne sait donc pas comment les autres moteurs réagissent.

La décision de signature est écrite : **aucun certificat aujourd'hui, et l'avertissement est
documenté**. L'écran 1 de l'installeur annonce SmartScreen, explique le geste, et renvoie aux
empreintes SHA-256 publiées avec chaque release. Aucun contournement d'heuristique n'a été
écrit ni envisagé.

#### Affirmations d'état levées (règle §5 bis)

« Pas de `pyproject.toml` : le projet n'est pas empaqueté » était vrai le jour où la phrase a
été écrite. Elle est **levée par un bloc daté** dans `core/version.py` — sans effacer
l'ancienne —, et le même geste est appliqué à `ruff.toml`, `.coveragerc` et
`requirements-dev.txt`, qui portaient la même. ⚠ Ce qui **tient** : le littéral Python reste la
source unique, et aucun parseur TOML n'est chargé au démarrage.

#### Corrigé en passant

- **`.github/workflows/ci.yml`** lisait `core.version.VERSION`, **un attribut qui n'existe
  pas** : l'étape « Version du projet » du job Sonar échouait sur un `AttributeError` et
  `sonar.projectVersion` partait vide. Corrigé en `__version__`.

#### Ce que le lot ne fait pas

Il ne redistribue **aucun** poids — ni détecteur, ni OCR, ni modèle de langue, ni poids
d'illustration —, n'installe ni Ollama, ni Pandoc, ni WeasyPrint, ni `unrar`, ni ComfyUI, ne
livre **aucune** mise à jour automatique, n'envoie rien sur le réseau sans opt-in, ne livre
pas de paquet Linux ni macOS (le prérequis est nommé : `PLAN-20` L20.2), ne réécrit ni ne
fusionne `config.yaml`, et ne change aucun comportement pour qui continue de lancer
`python gui.py` — ce que `tests/test_installation.py` vérifie fonction par fonction.

**Tests** : +141, **tous sans Qt** — 4 705 → **4 846** collectés avec PySide6, 4 289 →
**4 430** sans, l'écart de **416** rigoureusement inchangé et mesuré des deux côtés. La boucle
courte en exécute **4 789**, les mêmes 57 restant désélectionnés. Tout est dans
`docs/mesures/empaquetage-2026-09-06.md`, qui reprend les **seize critères du plan un par un**.
⚠ **Deux ne sont pas pleinement tenus** : le taux antivirus multi-moteurs n'est pas mesuré, et
le job de CI n'a jamais tourné sur un runner GitHub — ses trois vérifications ont été rejouées
à la main sur la machine principale.

## [2.30.0] - 2026-09-06

### MINEUR — Le premier lancement : le diagnostic dit quoi faire, les poids se récupèrent avec leur licence, et l'application sait se montrer sans œuvre

> **Rien n'est périmé, et il n'y a rien à réarmer.** `config.yaml` ne change pas d'une ligne —
> empreinte SHA-256 `77cb4bf3…`, **inchangée avant et après**. Aucun cache, aucun checkpoint,
> aucun prompt, aucun seuil, aucun format de sortie, aucune clé de configuration.
> `manga/checkpoints.py:FORMAT_VERSION` reste à **3**.
>
> ⚠ **La sortie console de `run.py --check` et de `run_manga.py --check` est INCHANGÉE, octet
> pour octet.** C'était la contrainte n° 1 du lot : ces deux commandes sont scriptées. Vérifié
> par `diff` sur les deux briques (section Ollama comprise) et gelé par
> `tests/test_core_diagnostic_iso.py` pour tout ce qui ne dépend pas du réseau.

#### Le défaut que ce lot corrige

L'interface affichait le diagnostic en **capturant la sortie console** des deux doctors et en la
posant dans une boîte de texte. Trois conséquences, toutes mesurées le 2026-09-06 :

- **aucun geste n'était attaché à un problème** — le texte disait ce qui manque, pas quoi faire ;
- **rien n'était réutilisable** : ni par l'accueil, ni par le dépôt guidé (qui a besoin de savoir
  si `unrar` existe **avant** de proposer un import), ni par un `.exe` qui devra se diagnostiquer
  chez l'utilisateur ;
- **le dialogue bloquait** pendant l'appel réseau — 12,1 s contre un serveur arrêté.

Et le pire cas ne se voyait nulle part. Mesuré : sans réseau et sans cache, `manga-ocr` lève un
`OSError` de `transformers` qui ne dit ni la cause ni le geste — et comme le lecteur est construit
paresseusement **dans le filet par planche**, l'échec se répète pour **chaque planche**. Un tome
de 150 planches produit 150 fois le même message obscur, ~18 minutes d'échecs, et aucune sortie.
Tout est dans `docs/mesures/premier-lancement-2026-09-06.md`.

#### Le diagnostic rend une structure

**`core/diagnostic.py`** (neuf) : un `Verdict` porte `identifiant`, `brique`, `gravite`,
`constat`, `consequence`, `geste`, `reparable`, et les lignes console exactes. Les deux doctors le
produisent ; ce sont les appelants qui impriment ou dessinent.

- **`ecrire` est un paramètre**, pas une capture. Là où le code appelait `print(x)`, il appelle
  `diag.dire(ecrire, x)` — qui écrit si on lui donne de quoi, et rend les lignes dans tous les
  cas. Le chemin console garde donc **le même texte, le même ordre et le même instant** ; une
  capture de `stdout` aurait laissé la console muette pendant les 12,1 s de la sonde LLM ;
- ⚠ **`gravite` est relative à une BRIQUE.** Pandoc absent est bloquant pour le light novel et
  pour lui seul : `diagnostic.bloquants_pour(sections, "manga")` n'en voit rien. L'affirmer
  découragerait quelqu'un qui n'a besoin que de planches. La réciproque est vraie et testée ;
- **une quatrième gravité, `conforme`,** que le plan n'avait pas prévue : un doctor rapporte aussi
  ce qui marche, et sans elle la structure ne pouvait pas reproduire les seize lignes `✓` de
  `run.py --check` — donc l'isométrie était impossible.

**`manga/doctor.py`** (neuf) : le diagnostic manga **quitte la CLI**. Il vivait dans
`run_manga._run_doctor`, et `gui/fenetre.py` faisait `from run_manga import _run_doctor` — la
fenêtre dépendait d'une CLI, l'inversion de couche exacte que le lot 2.6 avait défaite côté light
novel. `run_manga._run_doctor` reste et appelle la brique : rien de ce qui l'importait ne casse.

**`core/llm.py`** : `test_connection`, `_verifier_modeles` et `_essai_de_generation` gagnent un
paramètre `ecrire` **à défaut `print`**. La sortie de `run.py --test-llm` ne bouge pas.

#### La page Diagnostic, et les gestes qu'elle a le droit de proposer

**`gui/diagnostic.py`** et **`gui/vue_diagnostic.py`** (neufs ; le second sans Qt, comme le veut
la règle de couche). Le Diagnostic devient une **destination**, en pied de pane — la convention
Fluent range là les réglages, mais c'est une question de place, pas de nature.

Chaque manque porte son constat, sa conséquence et son geste. ⚠ **Aucun verdict non conforme n'est
affiché sans geste** — au pire « hors périmètre », explicitement.

**`core/reparations.py`** et **`manga/reparations.py`** (neufs) déclarent trois classes, et
elles décident de ce qui est permis :

| Classe | Exemples | Geste autorisé |
|---|---|---|
| récupérable | poids ONNX, modèle `manga-ocr`, polices du dépôt | téléchargement, licence affichée **avant**, SHA-256 enregistrée après |
| à installer soi-même | Pandoc, `unrar`, serveur LLM, WeasyPrint, ComfyUI | un lien, une commande copiable — **jamais un bouton** |
| hors périmètre | pilotes GPU, CUDA/ROCm | dire ce qui manque, et s'arrêter là |

Les quatre règles, et elles sont testées :

1. ⚠ **rien ne se télécharge sans un clic explicite** — `executer()` exige `consentement=True` ;
2. ⚠ **aucun téléchargement pendant un run** — et `run_en_cours=True` refuse avant toute lecture
   de configuration, pour qu'aucun ordre d'évaluation ne puisse contourner la règle ;
3. **la provenance est enregistrée** — URL, date, taille, SHA-256, licence — par
   **`core/provenance.py`** (neuf), dans une fiche posée à côté du poids ;
4. **un fichier partiel est détecté avant usage** (taille, `.part` résiduel, empreinte) et refait
   proprement, plutôt que chargé et laissé planter dans `onnxruntime`.

⚠ **Angelith n'installe aucun logiciel système**, et
`tests/test_core_reparations.py` le vérifie en lisant **les deux** modules par `ast` : aucun
appel de sous-processus ne nomme `winget`, `choco`, `apt`, `msiexec`… Le **seul** sous-processus
lancé de tout le lot est `tools/installer_polices.ps1`, qui enregistre des polices pour
l'utilisateur courant — pas de droits administrateur, réversible, et rien qui devienne un
service.

⚠ **Le partage entre les deux modules n'est pas du rangement : c'est la règle de couche.**
`core` n'importe aucune brique — c'est la ligne dont tout le reste du dépôt dépend
(`tests/test_imports_briques.py`) — et récupérer un poids de détection demande `manga.models`.
Le socle porte donc le **vocabulaire** (les trois classes, les refus, l'état d'un fichier) et les
entrées purement déclaratives ; la brique **enregistre ses gestes** à l'import. C'est le même
partage que pour les doctors, et la même raison. Conséquence assumée et écrite : une réparation
de brique est inconnue tant que le module de sa brique n'a pas été importé — on ne répare pas une
brique qu'on n'a pas chargée. Le message de refus le dit.

⚠ **Angelith ne redistribue aucun poids et n'héberge aucun miroir.** Le détecteur de texte sur
dessin est **GPL-3.0 + Manga109-s**, qui a ses propres conditions d'usage : il se récupère chez
son éditeur, et sa consigne le dit avant le clic. La licence de **LaMa** n'étant **pas établie au
2026-09-06**, il n'a aucune entrée dans le catalogue.

⚠ **Une exception, nommée** : `run_manga.py --check` télécharge toujours le détecteur manquant,
comme depuis la 2.9.0 — taper cette commande **est** le geste explicite, ouvrir une page ne l'est
pas. Le chemin structuré, lui, ne télécharge jamais.

#### Le premier lancement sans corpus

**`manga/demonstration.py`** (neuf) et le geste **« Créer un tome de démonstration »**, sur
l'accueil et dans le menu Fichier. ⚠ Il est dans la brique, pas dans le socle, pour la raison
ci-dessus : un tome de démonstration est un tome de **manga** — il écrit des `BubbleRegion`, des
checkpoints et une page nettoyée. Une installation neuve n'a aucune œuvre, et l'utilisateur ne
peut pas en fournir une pour essayer sans se poser la question des droits.

Le tome est fabriqué par le programme lui-même — deux planches, quatre bulles, redistribuable sans
réserve — avec ses checkpoints écrits d'avance, ce qui le rend retouchable et rendable **sans
aucun modèle et sans réseau**. Vérifié de bout en bout : `restart_from="rendu"` produit un **CBZ**
et, sur une configuration qui le demande, un **PDF** réels, en 4,8 s.

⚠ Il est **marqué** (`_Démonstration Angelith`, plus un `DEMONSTRATION.txt` qui dit ce qu'il est)
et **supprimable** — et `supprimer()` refuse d'effacer un dossier qui ne porte pas exactement ce
nom, comme `illustration/frontiere.py` refuse d'écrire hors du dossier de sa brique.

⚠ **Il se refuse proprement si la police manque**, en nommant la variable d'environnement, les
candidats essayés et la commande d'installation. `tests/conftest.py` a le droit de *skipper* ; une
application livrée à quelqu'un ne l'a pas. La police est résolue **avant** toute écriture : un
refus laisse le disque exactement comme il était.

#### La page « À propos » dit ce qui est là

Elle liste maintenant **les licences des poids réellement présents sur la machine**, lues dans les
fiches de provenance — et non la liste théorique de ce que le projet sait récupérer, qui reste
affichée à côté. Un poids sans fiche n'est crédité d'aucune licence : la page le dit et renvoie à
la source.

⚠ **Et elle tranche le nom.** Le contexte agent s'interrogeait depuis le 2026-08-26 ; au
2026-09-06 tout le code applicatif dit Angelith. C'est désormais écrit :
**« Angelith » est le nom public du logiciel, « Yume-Trad » le nom du dépôt de travail.**

#### Deux défauts trouvés par les tests du lot, et corrigés

- ⚠ **le rappel d'avancement des deux gestes neufs nommait un signal qui n'existe pas**
  (`signaux.journal` au lieu de `signaux.ligne`). Il levait dans le fil de travail avant le
  premier octet : un clic sur « Télécharger les poids » aurait produit une ligne d'erreur et rien
  d'autre. Trouvé par le test de bout en bout, corrigé, et gardé par un test qui vérifie que la
  licence atteint le journal **avant** le transfert ;
- **le marqueur du tome de démonstration est désormais écrit EN DERNIER.** `demonstration.existe()`
  veut donc dire « là **et complet** » : un demi-tome ne passe plus pour une démonstration, et un
  appelant qui attend « c'est prêt » n'a plus à courir après la fin d'une écriture. C'est ce
  changement qui a rendu le défaut précédent visible.

#### Ce que ce lot ne fait pas

- il n'empaquette rien, ne produit aucun `.exe`, ne crée pas `pyproject.toml` — c'est le lot 37 ;
- il ne modifie aucun seuil, aucun prompt, aucun chemin de traitement ;
- il ne rend pas la brique illustration diagnosticable : ComfyUI n'a pas de verdict, seulement une
  consigne d'installation ;
- ⚠ **il ne corrige pas les 150 échecs de `manga-ocr` sans réseau.** Le cas est rendu *évitable*
  (le modèle se récupère avant le run), pas impossible : le corriger demanderait de toucher au
  filet par planche de l'orchestrateur, hors du périmètre. C'est nommé dans le document de mesure
  comme candidat n° 1 d'un correctif ultérieur.

#### Mesure

`docs/mesures/premier-lancement-2026-09-06.md` — le tableau de masquage dépendance par
dépendance, le cas `manga-ocr` chiffré, les douze critères du plan un par un, et ce que la mesure
ne dit pas. ⚠ **Une prémisse du plan y est corrigée plutôt que recopiée** : `torch` *est*
installé dans cet environnement, contrairement à ce que le plan supposait — la conclusion qu'il en
tirait reste juste, la prémisse était une observation, pas une propriété du dépôt.

**+138 tests** (4 567 → **4 705** avec PySide6 ; 4 175 → **4 289** sans, l'écart passant de 392 à
**416**), dont **114 sans Qt** — les deux colonnes relevées, pas déduites. La boucle courte en
exécute **4 648**, les mêmes 57 restant désélectionnés.

Redémarrage de l'accueil revérifié avec le serveur LLM arrêté : **0,138 s** avant le premier
pixel, 1 fichier ouvert, un seul panneau construit.

## [2.29.0] - 2026-09-05

### MINEUR — La retouche devient une destination : le tome reçu, la garde nommée, le cache qui cesse de s'emballer

> **Rien n'est périmé, et il n'y a rien à réarmer.** `config.yaml` ne change pas d'une ligne —
> empreinte SHA-256 `77cb4bf3…`, **inchangée avant et après**. Aucun cache, aucun checkpoint,
> aucun prompt, aucun seuil, aucun format de sortie, aucune clé de configuration.
> `manga/checkpoints.py:FORMAT_VERSION` reste à **3**, et `tests/test_caches_intacts.py` le
> vérifie désormais à chaque exécution — sur des **copies** des caches réels du corpus.
>
> ⚠ **Un changement de comportement visible, et il est le correctif du lot :** l'éditeur ne
> précharge plus que ce que le plafond de son cache d'aperçus peut garder. Détail plus bas —
> la sortie rendue, elle, est identique au pixel près.

#### Le défaut que ce lot corrige, et il ne se voyait nulle part

L'étape 0.1 du `PLAN-35` demandait de chiffrer l'ouverture d'un tome dans la retouche. Elle a
trouvé autre chose : **le cache d'aperçus s'emballait**, avec les réglages par défaut, sur un
tome ordinaire.

`gui/cache_apercu.py` annonçait depuis la 1.5.0 : « la fenêtre ±10 du préchargement pèse
~21 Mo ; le plafond par défaut (120 Mo) la contient largement ». Les deux moitiés sont fausses.

| | annoncé | mesuré le 2026-09-05 |
|---|---:|---:|
| un aperçu, tome paginé (118 planches, 1440×2048) | 1,04 Mo | **9,35 Mo** |
| un aperçu, bande webtoon (1080×10 000) | — | **35,2 Mo** |
| la fenêtre ±10 au milieu d'un tome (21 planches) | ~21 Mo | **~196 Mo** |

Le plafond n'en tenait donc que 12 sur 21. Le cache évinçait, `travail_restant` redemandait,
la voie de lecture recomposait — sans fin. Mesuré au rang 60 d'un tome de 118 planches, sur un
éditeur que personne ne touchait : **137 compositions pour 12 aperçus gardés en 120 s**, soit
un cœur occupé en permanence. Après le lot : **13 pour 12**. Sur la bande webtoon,
**14 → 3**, et le pic mémoire du processus passe de 1 047 à 979 Mo.

`gui/cache_apercu.py` gagne `fenetre_tenable` et `fenetre_retenue`, sans Qt et testées : la
fenêtre ne demande plus que ce que le plafond garde, la planche courante restant toujours au
centre. ⚠ **Tant qu'aucun aperçu n'a été composé, rien n'est bridé** — deviner un poids
reviendrait à remplacer une valeur fausse par une autre ; c'est le premier aperçu réel qui
donne la mesure, et `apercu_pret` resserre la fenêtre à ce moment-là.

⚠ **Le chiffre de 1,04 Mo n'est pas effacé du fichier** : il est daté, encadré, et démenti
sur place — règle des affirmations d'état (`00-CONTEXTE-AGENT.md` §5 bis).

#### La garde de travail non enregistré : six chemins nommés, trois qui ne demandent rien

Le `PLAN-31` avait fait de la retouche une destination parmi sept et annonçait un trou : en
quitter une deviendrait un changement de destination que rien ne garderait. **La mesure dit que
le trou ne s'ouvre pas**, et le lot le prouve plutôt que de le supposer.

`gui/garde.py` (sans Qt) porte les six chemins de l'étape 0.2, chacun avec son verdict et son
motif ; `Fenetre.peut_quitter(chemin)` est l'**unique** implémentation, et les six l'appellent :

| Chemin | Perd le travail ? | Ce qui se passe |
|---|---|---|
| changer de tome | oui | boîte à trois choix, inchangée depuis le lot 18 |
| changer de projet | oui | même boîte — chemin nommé à part, il se compte à part |
| **changer de destination** | **non** | **aucune boîte** : les pages vivent dans un `QStackedWidget`, en quitter une la cache |
| fermer la fenêtre | oui | même boîte, et c'est désormais le même code |
| lancer un run global | non | le run VERROUILLE le tome, il ne le jette pas |
| créer un projet | non | n'écrit que sous `sources/` d'un tome neuf |

⚠ **Aucune garde n'a été ajoutée, et c'est délibéré.** « Un dialogue qui se pose à chaque
changement d'onglet est un dialogue qu'on apprend à cliquer sans lire, et c'est la façon la
plus sûre de perdre du travail avec une garde en place. » Un test le vérifie avec trente
planches en attente.

#### Le miroir de récupération existe, il écrit — et il annonçait deux planches de trop

L'infobulle du lot 18 promettait « un miroir de récupération écrit toutes les 30 s ». La
promesse est tenue : minuteur à 30 000 ms, actif, cinq fichiers écrits par planche, état
relu à l'identique. Le test qui le prouve manquait ; il existe.

Mais `recuperation.planches` comptait **tout** dossier `page_NNNN`, vide compris — et le
corpus en portait : sur la bande webtoon, deux dossiers vides à côté d'un seul complet. La
boîte de reprise annonçait donc « 3 planches portent des modifications non enregistrées »,
en récupérait une, et sortait deux « brouillon illisible ». Elle compte maintenant les
brouillons **lisibles**. ⚠ Le mode de panne n'est pas symétrique : ne pas annoncer un
brouillon lisible perdrait du travail, alors qu'annoncer un dossier vide ne coûtait qu'un
message — un test garde le côté cher.

#### Ce que la destination Retouche dit maintenant

- **pourquoi un tome n'est pas dans la liste.** Un projet qui porte un roman *et* son manga
  n'affiche que ses tomes de planches ; la note nomme les absents et dit où les traiter. Une
  liste qui filtre sans le dire est une liste qu'on croit complète ;
- **ce que le verrou de run protège.** Il grisait en disant « … — affichage seul ». Il dit
  maintenant « Verrouillé : run en cours sur Manga · Mon Manga / Vol.2 — Traduction et rendu
  (5/6) — planche 84/131 — affichage seul », et il offre le seul geste utile : **Arrêter
  proprement** — le même `core.control.request_stop` que `--stop`, pas un second mécanisme ;
- **ce que le cache coûte.** « aperçus 3/9 en cache — 105,6 Mo sur 120, ~35,2 Mo pièce », avec
  l'infobulle qui nomme `gui.apercu.plafond_mo`. Le chiffre n'apparaît qu'à partir de deux
  aperçus : une moyenne tirée d'un seul décrirait la planche qu'on regarde, pas le tome.

#### « Retoucher » marche à chaque fois, et un run terminé y mène

`demande_retouche` de la bibliothèque était branché sur `ouvrir_tome`, qui ne navigue que si la
destination n'a jamais été construite : le bouton marchait **la première fois** et paraissait
sans effet ensuite — le tome s'ouvrait bien, derrière la bibliothèque restée à l'écran.
`Fenetre.retoucher` ouvre **et** amène.

Le chemin inverse existe aussi : le bilan d'un run manga porte « Retoucher 3 planches » quand
le dépôt sait lesquelles (`_planches_du_run`), « Retoucher ce tome » sinon — jamais un compte
inventé. Un run light novel ne propose rien : il n'y a pas d'éditeur light novel dans ce dépôt.

#### La bande webtoon : ce que la mesure autorisait, et ce qu'elle n'autorisait pas

Le `PLAN-35` L35.3 était conditionnel et permettait de conclure « rien à faire ». La mesure
justifie d'agir, mais pas d'aller aussi loin que le plan l'autorisait :

- ✅ **livré** — la mémoire mesurée, affichée, et le frein de fenêtre ci-dessus ;
- ❌ **non livré** — la navigation par segment et l'aperçu partiel. Les deux demandent de
  toucher `gui/scene_planche.py` et `gui/editeur.py`, ce que le §4 du plan écarte
  explicitement (« il ne réécrit pas l'ergonomie de l'éditeur »). Le motif et le seuil qui
  les justifieraient sont publiés.

⚠ **Une prémisse du plan était fausse.** Il annonce la bande webtoon comme « 1 bande /
chapitre ». Le chapitre du corpus en porte **neuf**, de 1080×10 000 chacune. La question
« que fait la fenêtre glissante quand il n'y a qu'un seul élément à précharger ? » n'a donc pas
de cas dans ce corpus.

⚠ Tout chiffre webtoon de ce lot porte sa réserve : **une seule bande au corpus, également le
seul volume à source latine** — les deux effets sont confondus.

#### Ce qui n'a pas changé

- `Tome` et `Services` restent construits et libérés par la **fenêtre**, un seul vivant à la
  fois ; un test compte les instances sur quatre ouvertures successives ;
- `editeur.ouvrir` n'est appelé par aucun chemin de démarrage — le critère du `PLAN-31` reste
  vert, et il a maintenant son test dans les deux fichiers ;
- ni `FilDeTravail`, ni `FilDeLecture`, ni le relais de verrou ne quittent la fenêtre ;
- aucun geste d'édition nouveau, aucun éditeur light novel, aucune mise en file derrière un
  run global.

Tout est dans [`docs/mesures/retouche-2026-09-05.md`](docs/mesures/retouche-2026-09-05.md),
qui reprend les **douze critères du plan un par un**, y compris ceux qui ne sont pas tenus.

---

## [2.28.0] - 2026-09-05

### MINEUR — La bibliothèque des œuvres : l'état sur une page, le dépôt guidé, l'export du glossaire

> **Rien n'est périmé, et il n'y a rien à réarmer.** `config.yaml` ne change pas d'une ligne —
> empreinte SHA-256 `77cb4bf3…`, **inchangée avant et après**. Aucun cache, aucun checkpoint,
> aucun prompt, aucun seuil, aucun format de sortie, aucune clé de configuration. Le lot ne
> produit **aucun nouveau format** : il montre et il réunit ce qui existe.
>
> ⚠ **Deux changements de comportement visibles**, tous deux volontaires :
> · **lâcher des planches sur la fenêtre ouvre désormais le dépôt GUIDÉ** et non plus la boîte
>   « Nouveau projet ». Ce qui manquait n'était pas la création, c'était ce qui vient après le
>   lâcher — le compte rendu de ce qu'on a lâché, la collision nommée, le coût annoncé ;
> · **un glossaire `.csv` s'importe vraiment.** `gui/depot.py` l'annonçait depuis le lot 18 ;
>   `core/glossary_import._to_text` levait « Format non géré ». Voir plus bas.

#### `run_manga.py --list` : un seul inventaire, deux affichages — et la sortie ne bouge pas

La CLI consomme le même `bibliotheque.py` que la destination « Œuvres ». **La sortie console
est iso**, comparée ligne à ligne sur les 18 œuvres du corpus (110 lignes, `diff` vide), et son
coût aussi : `--list` sur une œuvre jamais traitée passe de 719 ms à 673 ms, sur une œuvre
terminée de 1 941 ms à 1 918 ms — dans le bruit d'un lancement de processus.

⚠ La colonne d'état reste le verdict de la brique **manga** (`manga/serie.py`), y compris sur
un tome de roman, où il vaut « aucune image ni archive ». C'est la réponse juste à la question
que pose `run_manga.py`. Le statut multi-brique, plus riche, ne sert qu'à la vue.

#### Le corpus fait 18 œuvres, pas 17, et un tome porte deux briques

Le `PLAN-34` — comme les six autres de la série et `00-CONTEXTE-AGENT.md` — annonce **17
projets sous `sources/`**. Il y en a **18** : 55 tomes, **3 493** planches et pages source
dénombrées, 15 tomes indénombrables sans extraction, 14 glossaires, **791** entrées.
`tools/inventaire_oeuvres.py` produit le tableau, son chronomètre et son compteur d'appels
système ; `--anonyme` le rend publiable sans nommer une seule œuvre sous droit d'auteur.

Et `TomeInfo.brique` ne pouvait pas être un `str` : `sources/manga C/Vol.1/`
porte **`manga/`** (165 planches rendues) **et** `JAP/` (271 images, brique scan). Le modèle
porte donc les deux, et le filtre interroge la liste — sans quoi filtrer sur « Scan » faisait
disparaître le seul tome du corpus qui en porte un aux côtés de ses planches.

#### ⚠ `core/bibliotheque.py` était interdit par le dépôt — le module vit à la racine

Le plan demandait le module « dans `core/`, parce qu'il couvre les deux briques ». C'est
exactement le raisonnement qui l'en exclut, et deux tests existants le refusent :
`test_le_socle_ne_depend_pas_du_pipeline` et `test_le_socle_nimporte_ni_les_briques_ni_les_cli`.
La première version du lot les a fait échouer — c'est ainsi que la contradiction s'est vue. Le
socle est ce dont les briques dépendent ; l'agrégateur des quatre briques vit donc à la
**racine** (`bibliotheque.py`), la couche de `app.py` et des quatre `run_*.py`.

#### 78 % des appels système du balayage supprimés — et deux défauts anciens avec

Le balayage des 18 œuvres passe de **2 205 ms à 1 250 ms** et de **16 169 à 3 574** appels
système (`os.stat` : **13 667 → 1 151**, −92 %). Trois causes, toutes antérieures au lot et
toutes corrigées **sans changer un seul verdict** :

- `sources_manga.resoudre_source` payait un `os.stat` **par entrée** de `<Tome>/manga/` pour
  trouver ses dossiers de langue : **5 928 appels** sur le corpus, pour zéro à trois dossiers.
  `sources_manga.sous_dossiers()` fait un `os.scandir` ;
- `etat_planches.motifs_de_peremption` paie cinq `os.stat` par planche : **5 470 appels**.
  `etat_planches.balayer_tome()` lit tout un tome en un `scandir` par planche. ⚠ **La règle de
  péremption reste écrite une seule fois** (`etat_planches._motifs`) et les deux chemins
  d'accès l'appellent — un test refuse qu'ils divergent ;
- `etat_planches.indices_de` avait le même défaut, pour **1 102 appels**.

Ces trois correctifs profitent aussi à `--list`, à l'assemblage et à l'éditeur.

⚠ **Le cache que le plan demandait au-delà d'une seconde n'est PAS livré, et c'est une
décision.** La seule clé d'invalidation praticable — le `mtime` des dossiers de build — est
fausse : réécrire `traduction_manuelle.json` dans `page_0042/` ne déplace pas le `mtime` de
`.checkpoints/`. Un tel cache afficherait « à jour » sur un tome qu'on vient de corriger à la
main, c'est-à-dire le défaut exact que `manga/etat_planches.py` existe pour empêcher. À la
place : les appels supprimés, quatre fils (le balayage est bloqué sur le disque), la
mémoïsation en mémoire (**1,4 ms** au second affichage), le balayage hors du fil d'affichage,
et un bouton « Rafraîchir » explicite.

#### L'export du glossaire, qui n'existait pas

`core/glossary_export.py` — un format d'**archive** et deux **vues**, et la différence est
écrite dans les fichiers produits :

| Format | Statut | Aller-retour |
|---|---|---|
| **YAML** | archive | garanti — **testé sur les 14 glossaires réels du corpus**, structures comparées |
| **CSV** | vue | possible, perte **nommée en tête du fichier** |
| **Markdown** | vue de relecture | ne se réimporte pas fidèlement, et le dit |

Le plus gros glossaire du corpus est nommé : **manga D, 124 entrées, 38 359 octets**.
Chaque fichier produit porte sa provenance — œuvre, tome d'où part l'export, version
d'Angelith, date, nombre d'entrées, langue cible — parce qu'un glossaire qui circule sans
dénominateur ne se fusionne pas. Et **l'export ne touche jamais sa source** : il passe par
`yaml.safe_load`, jamais par `glossary.load`, qui migre et réécrit le fichier qu'il ouvre.

⚠ **La perte du CSV est mesurée, pas supposée** : sur les 14 glossaires réels, l'aller-retour
conserve noms, catégories, genres, variantes, formes interdites et descriptions. Ce qu'il perd
est écrit dans le fichier : les rendus des autres langues cibles, `a_romaniser`, et la
différence entre un champ vide et un champ absent.

#### `core/glossary_import.py` : le `.csv` et les lignes de commentaire

Deux défauts, trouvés en écrivant l'export :

- **`.csv` n'était pas importable**, alors que `gui/depot.py` l'annonce depuis le lot 18 —
  `_to_text` levait « Format non géré », et le point-virgule ne figure pas dans `_SEPARATORS`.
  `parse_file` route désormais un `.csv` produit par le dépôt vers un vrai lecteur CSV (avec
  ses catégories, genres, variantes et formes interdites) ; tout autre `.csv` retombe sur le
  parseur tolérant ;
- **une ligne de commentaire devenait une entrée de glossaire.** `# Le glossaire est propre à
  l'ŒUVRE : il vaut pour tous ses tomes.` était découpé sur le « : » et enregistré comme un
  terme. Une ligne `#` non reconnue comme section, et une citation Markdown `>`, sont
  désormais ignorées — sans quoi l'en-tête d'avertissement de l'export se serait réimporté en
  fausses entrées, ce qui aurait été pire que pas d'avertissement.

#### Le dépôt guidé, jusqu'au bout du geste

`gui/depot_guide.py`, sans Qt : ce qu'on a lâché (le contenu d'une archive **listé sans
l'extraire**), où ça va (prérempli, corrigible), la collision **nommée**, le coût annoncé avant
le premier octet.

⚠ **Copier reste le défaut.** « Déplacer » existe, décoché, non persisté, et confirmé — un
lâcher qui vide le dossier d'origine est irréversible, et c'est le geste le plus facile à
déclencher par accident de toute l'interface.

⚠ **Un `.cbr` est refusé AVANT l'import** quand `rarfile` ou l'outil externe `unrar`/`unar`
manque, avec le motif exact. L'échec remontait jusqu'ici en `SystemExit` depuis
`manga/ingest.py`, au milieu de la copie, après que l'utilisateur avait nommé son projet. La
sonde définitive appartient au `PLAN-36`, non livré : celle-ci est minimale et écrite pour être
remplacée.

#### Les sorties d'un tome, réunies sans être refaites

`gui/sorties.py` montre ce qui existe **sur le disque** avec sa date et sa taille, et ce qui
n'existe pas avec le geste qui le produirait **et son coût**.

⚠ **Aucun bouton ne lance un run** : le geste est une *chaîne* à recopier, jamais un appelable.
Un « Exporter en PSD » qui relancerait le rendu de 131 planches sans le dire serait la pire
action coûteuse sans garde-fou de l'application. Et le refus du format PSD au-delà de 30 000 px
s'affiche comme un **état**, pas comme une erreur — la 2.6.0 a livré ce refus propre plutôt
qu'un fichier corrompu.

#### Ce que la vue refuse

**Aucune vignette d'œuvre, même désarmée** : ce sont des œuvres sous droit d'auteur, et une
grille de couvertures est la capture d'écran qu'on ne pourra jamais montrer. **Aucune
suppression** : la corbeille d'une application qui gère des heures de GPU est un lot à elle
seule. **Aucun état dit par la couleur seule** : chaque état est un caractère (`●◐○↻`),
l'infobulle nomme chaque étape en toutes lettres, et la légende reste en barre d'état même
repliée.

#### Fichiers

Neufs : `bibliotheque.py`, `core/glossary_export.py`, `gui/depot_guide.py`, `gui/sorties.py`,
`gui/vue_oeuvres.py`, `tools/inventaire_oeuvres.py`.
Modifiés : `gui/oeuvres.py` (l'état vide nommé du lot 31 devient la bibliothèque),
`gui/dialogues.py` (trois boîtes), `gui/fenetre.py`, `gui/travailleur.py`
(`GENRE_BIBLIOTHEQUE`, **sans verrou** : il ne fait que lire), `manga/creation_projet.py`
(`deplacer=`), `manga/etat_planches.py`, `manga/serie.py`, `manga/sources_manga.py`,
`core/glossary.py` (`entete=`), `core/glossary_import.py`, `run_manga.py`.

**Les six modules NEUFS sont tous sans Qt** ; les deux fichiers Qt touchés existaient déjà.
**+109 tests, dont 84 sans PySide6** — les décisions d'affichage de la bibliothèque ont dû
quitter `gui/oeuvres.py` pour `gui/vue_oeuvres.py`, sans quoi leurs tests étaient impossibles
à collecter dans le job de CI qui ne l'installe pas. Tout est dans
[`docs/mesures/bibliotheque-2026-09-05.md`](docs/mesures/bibliotheque-2026-09-05.md), qui
reprend les douze critères du plan un par un — **y compris les deux qui ne sont pas tenus** —
et publie ce que la mesure ne dit pas.

## [2.27.0] - 2026-09-05

### MINEUR — Les quatre lanceurs : un formulaire déclaré, le run de nuit, le choix du modèle, les profils

> **Rien n'est périmé, et il n'y a rien à réarmer.** `config.yaml` ne change pas d'une ligne,
> et son empreinte SHA-256 est **inchangée avant et après un run lancé depuis l'interface avec
> chaque paramètre modifié** — un test la compare (`tests/test_gui_lanceur.py`). Aucun cache,
> aucun checkpoint, aucun prompt, aucun seuil, aucun format de sortie. Aucune clé de
> configuration n'est ajoutée : tout réglage de run est une mutation du dictionnaire **en
> mémoire**, exactement comme un drapeau de ligne de commande.
>
> ⚠ **Deux changements visibles à l'écran**, tous deux volontaires :
> · la destination **Light novel** n'affiche plus « Planches par appel » ni « Raisonnement ».
>   Ils y étaient posés inconditionnellement depuis le lot 18 et **n'avaient aucun effet** :
>   `run.py` ne connaît ni `--lot` ni `--think` ;
> · la case « Éteindre le PC à la fin » rejoint `force` et `dry_run` dans les réglages
>   **jamais persistés**. Un fichier `.angelith/interface.json` qui la portait ne l'arme plus.
>
> ⚠ **Un repli interne disparaît** : `PanneauLanceur` exige désormais sa `brique`. Le mode
> « brique libre », sans appelant depuis le lot 31 et sans test, est retiré — les paramètres
> offerts dépendent de la destination, donc changer de brique en session devrait reconstruire
> tout le formulaire.

#### Le relevé du plan était faux de 11 arguments, et le script le montre

`tools/inventaire_drapeaux.py` lit les quatre CLI avec `ast`, **résout
`cli.ajouter_flags_veille`**, et croise le résultat avec la table des paramètres. Le `PLAN-33`
annonçait 82 arguments au total ; il y en a **93**. Neuf de l'écart sont les drapeaux de
veille, qui ne sont écrits dans aucune des trois CLI qui les portent ; deux sont les options
de bande nées au lot 31.

| | exposés par le formulaire | ailleurs (bouton, menu, cible) | non exposés, motivés | non classés |
|---|---:|---:|---:|---:|
| 93 arguments | **24** | **26** | **43** | **0** |

`tests/test_inventaire_drapeaux.py` échoue si un drapeau neuf apparaît sans être classé —
**et** si un motif survit au drapeau qu'il justifiait.

#### `gui/parametres.py` — dix-neuf paramètres déclarés, un seul générateur

Une table gelée, sans Qt, sur le patron de `gui/actions.py` et `gui/destinations.py`.
`gui/formulaire.py` la dessine pour les quatre destinations de lancement, et pour les trois
lignes de même nature de l'atelier d'illustration (`construire_dans`, qui les pose dans **sa**
mise en page : l'atelier n'est pas démembré).

| Destination | réglages utiles avant | après |
|---|---:|---:|
| Light novel | 5 | **9** |
| Manga | 7 | **14** |
| Webtoon | 9 | **16** |

La règle du défaut « selon `config.yaml` » — écrite au lot 18 pour le seul menu `--think`, et
dont le motif est qu'un `think: false` écraserait aussi l'`endpoint:` de l'agent — est
**généralisée à tous les paramètres à trois états**, et testée contre le vrai `config.yaml` :
un formulaire laissé à ses défauts ne pose **aucune** clé.

Entrent dans l'interface : `--langue`, `--conf`, `--iou`, `--keep-awake`, `--shutdown`,
`--shutdown-delay`, et le choix du modèle.

#### Le run de nuit entre dans l'interface

L'interface graphique était **la seule des trois** à ne pas pouvoir en lancer un, dans un
dépôt qui a une branche nommée `run-de-nuit-v1.7.0`.

L'anti-veille vit dans la tâche (levée par un `finally`, même si le run lève) ; l'extinction
vit dans la fenêtre, parce qu'elle commence quand le travail est fini et doit rester annulable
pendant deux minutes. `gui/extinction.py` porte la décision, **sans Qt** : elle éteint après
un échec et n'éteint pas après un arrêt demandé, exactement comme `core/cli.finalize_power`.
Le compte à rebours est une quatrième ligne du bandeau de run, avec « Annuler l'extinction » —
et une ligne de journal part au moment où il commence, pas à la fin.

⚠ **`--all` n'entre pas.** C'est un enchaînement, pas un paramètre : le pré-vol, l'isolation
par chapitre et `RAPPORT-SERIE.md` sont écrits pour une console. Le motif complet est dans
`gui/parametres.NON_EXPOSES` et dans `docs/mesures/lanceurs-2026-09-05.md` §5. Un run de nuit
sur **un** tome est lançable ; l'œuvre entière reste `run_manga.py --all`.

#### `core/modeles.py` — le choix du modèle, et ce que l'endpoint refuse de dire

`GET /v1/models` rend **384 octets et quatre identifiants**, rien d'autre : ni capacité
vision, ni fenêtre de contexte. `GET /api/tags` (Ollama seulement) donne la vision, et donne
un `context_length` de 262 144 qui est celui de l'**architecture** et non celui que le serveur
sert — le piège que `core/power.contexte_charge` documente depuis la 2.12. L'interface affiche
donc « vision : inconnu » là où elle ne sait pas, **avertit** quand la brique manga en dépend,
**ne filtre jamais** la liste sur une devinette, et **n'affiche aucune fenêtre de contexte**.

Le modèle choisi outrepasse la spec des agents **en mémoire**, conserve l'`endpoint:` de
chacun, laisse à `null` ceux qui y sont, et **nomme** au récapitulatif tous les agents qu'il
change. Aucune écriture dans `config.yaml`, aucun `ollama pull` — c'est le `PLAN-36`.

⚠ **Mesuré en chemin** : `localhost` coûte **2,04 s** contre **0,003 s** pour `127.0.0.1` sur
cette machine Windows, pour la seule résolution de nom. Or le défaut du dépôt est
`http://localhost:11434/v1`. Le délai de la sonde de modèles est fixé à 6 s en conséquence.

#### `gui/profils.py` — des raccourcis de saisie, pas des mandats

`.angelith/profils.json`, un profil par destination. Il ne porte **jamais** `force`,
`dry_run`, `shutdown`, ni le projet et le tome. Le filtre est triple, et le troisième compte
autant que les deux autres : `nettoyer()` lave aussi un fichier **écrit à la main**.

#### La brique scan reste hors de l'interface, et c'est écrit

Décision du `PLAN-33` étape 0.3, tranchée par écrit : elle est bêta depuis la 1.4.0, sa seule
mesure publiée est un débit (« ~2 h pour 270 pages »), et **aucune mesure de qualité de
lecture n'existe**. Une destination qui porterait « bêta » sans pouvoir dire ce que la lecture
vaut promettrait un rang qu'on ne peut pas tenir. Motif complet dans
`gui/parametres.NON_EXPOSES` (les dix-huit arguments de `run_ocr.py`) et
`docs/mesures/lanceurs-2026-09-05.md` §4.

#### Le refus qui reste

**Aucune boîte de confirmation n'annonce une durée de run.** Le refus du lot 18 est gardé, et
un test le vérifie : « aucune constante mesurée ne couvre un run complet — l'annoncer serait
inventer un chiffre ». Ce qui s'affiche porte son dénominateur, et un test refuse un coût
déclaré qui n'en a pas.

⚠ Une prémisse du plan a été trouvée **fausse à la mesure** et n'a pas été recopiée : le
« 10,8 Mo sur une bande webtoon 1080×10 000 » qu'il attribuait à `fenetre_hauteur` est en fait
le coût de `aire_min_composante` (`config.yaml` L894). L'infobulle porte à la place ce que le
fichier mesure de la fenêtre : **7,1 s par bande fenêtrée contre 0,85 s** pour une inférence
unique, sur les 9 bandes du chapitre de référence.

**Tests** : 4 239 → **4 378** (`pytest --collect-only -q`, 2026-09-05), dont **4 039 sans
PySide6** — les deux colonnes relevées, l'écart passe de 292 à **339**. La boucle courte en
exécute **4 321**, les mêmes 57 restant désélectionnés.

**Mesure complète** : [`docs/mesures/lanceurs-2026-09-05.md`](docs/mesures/lanceurs-2026-09-05.md)
— les treize critères du plan un par un, y compris les deux non tenus.

---

## [2.26.0] - 2026-09-05

### MINEUR — Le run se regarde : des phases, l'objet en cours, une barre qui ne recule plus, et plus aucun pourcentage

> **Rien n'est périmé, et il n'y a rien à réarmer.** `config.yaml` ne change pas d'une ligne,
> son empreinte est inchangée. Aucun cache, aucun checkpoint, aucun prompt, aucun seuil,
> aucun format de sortie de fichier. **La sortie console est identique octet pour octet** — un
> test le vérifie sur un vrai `--dry-run`.
>
> ⚠ **Un changement de sortie, et il est à l'écran : le pourcentage disparaît.** La barre
> affichait `84 / 131 (64 %)` ; elle affiche maintenant `planche 84 / 131` et la phase. Le
> motif est mesuré et il est dans `docs/mesures/progression-2026-09-05.md` § 3 : la fraction
> du dépôt est *comptée*, pas *pondérée*, et « 64 % » se lisait comme 64 % du temps alors que
> la moitié des planches du balayage A ne coûte que ~32 % du run.

#### Le défaut, chiffré avant d'être corrigé

`tools/tracer_progression.py` reconstruit, depuis les 24 `perf.log` de `build/`, ce que le
canal de progression a dit pendant **36 runs réels**. Le verdict, sur les trois traces
versionnées dans `tests/corpus/progression/` :

| trace | reculs | dénominateurs distincts | sans temps restant affichable |
|---|--:|--:|--:|
| manga paginé, 150 planches | 2 | 1 | 63 s — 2,6 % |
| bande webtoon, 9 planches | 2 | 1 | 160 s — 44,2 % |
| **light novel, 25 chapitres** | **66** | **6** | **39 635 s — 89,7 %** |

Onze heures d'un run de douze sans la moindre estimation. Le pire cas du corpus est un run de
**15 h 26 dont 14 h 59 sans estimation**, avec **132 reculs**.

⚠ **Le plan se trompait sur la cause.** Il attendait le coût des deux changements de régime du
manga ; côté manga c'est effectivement négligeable. Le défaut grave est côté **light novel**,
et il tient à une ligne : `ReporterQt.block` émettait la progression, alors qu'un bloc
redémarre à 1 à chaque étage de chaque chapitre.

#### `core/progression.py` — le modèle, sans Qt et sans horloge murale

Des phases déclarées, un objet en cours, et une fraction **monotone par construction** : elle
se compose de `part`, c'est-à-dire du nombre de fois où le run traverse la collection — un
fait de structure du code, pas une estimation. Un filet (`_plancher`) la garde monotone même
là où le raisonnement suffirait, exactement comme l'invariant pixel de `manga/clean.py`.

Rejouées dans ce modèle, les trois traces donnent **0 recul** et ramènent le temps sans
estimation à **6,9 %** côté light novel, **1,7 %** côté manga.

`gui/avancement.py:Estimateur` n'est **pas** remplacé : il est utilisé, et nourri d'un débit
qui ne recule plus. Son vidage de fenêtre sur recul reste en place — il est juste le jour où
un canal recule pour de bon.

#### Le protocole `Reporter` gagne deux canaux, muets en console

- `progres(courant, total, objet="")` — argument **optionnel**, donc tous les appelants
  d'avant restent valides. L'objet arrive chiffré au lieu de voyager dans un libellé humain ;
- `phase(identifiant, libelle="")` — **méthode neuve à corps vide**. C'est le canal qui
  manquait : sans lui, deux balayages sur le même dénominateur sont indiscernables.

Les deux sont muets dans `Reporter` comme dans `RichReporter`.
`tests/test_reporter_protocole.py` vérifie que **tous** les reporters du dépôt — doubles de
test compris — portent le protocole entier : le premier double qui ne le portait pas a fait
tomber un `process_volume` sur un `AttributeError`.

Les orchestrateurs annoncent leurs phases (`manga/orchestrator_manga.py`,
`pipeline/orchestrator.py`) sans qu'aucun ordre d'étape, aucune frontière d'arrêt propre ni
aucun checkpoint ne change. **Une seule boucle gagne un appel de progression qu'elle n'avait
pas** : la passe terminologique du manga, entièrement muette jusqu'ici — jusqu'à 23,1 % du
temps instrumenté d'un run neuf, pendant lesquels la barre ne bougeait pas d'un pixel.

#### `gui/bandeau.py` — le bandeau de run, visible depuis les sept destinations

Il appartient à la **fenêtre**, pas à une destination : un run se regarde depuis la retouche
comme depuis l'accueil.

```
Manga · Mon Manga / Vol.2                      Traduction et rendu (5/6)
███████████████████░░░░░░░░░░  planche 84 / 131   ~1 h 10 restantes
page_0084.png · lot 80→99 · 3 planches par appel        [Arrêter proprement]
```

- **temps restant, jamais temps écoulé**, sans fausse précision ;
- **indéterminé = ni pourcentage, ni temps** — les trois cas légitimes sont nommés plutôt que
  chiffrés : un lot de traduction en vol, le chargement du modèle ONNX de détection, une
  génération d'image avant la première image écrite ;
- **l'objet en cours est nommé** ;
- `Arrêter proprement`, avec l'infobulle du lanceur, mot pour mot ;
- **rien n'y clignote**, et il disparaît quand aucun run ne tourne.

Le journal reste : le bandeau ne le remplace pas, il cesse d'obliger à le lire pour savoir où
on en est.

#### La fin d'un run se remarque, sans voler le focus

Un état terminal persistant — « Terminé — 131 planches, 2 h 14, 3 avertissements » — avec un
bouton qui ouvre les avertissements du run. **Aucune boîte modale** : l'utilisateur peut être
en train de taper une réplique dans la retouche, et un dialogue qui surgit avale la frappe.
Aucune notification système n'est livrée non plus, et le document de mesure dit pourquoi.

#### Le titre de fenêtre porte l'avancement, pour la barre des tâches

`84/131 — Manga · Mon Manga / Vol.2 — Angelith 2.26.0 [*]`. Le gabarit est **préfixé**, jamais
recomposé : `[*]` est l'emplacement où Qt insère la marque « document modifié », et une
concaténation naïve l'aurait perdu. Les quatre combinaisons (run / pas de run × modifié / pas
modifié) sont testées.

⚠ **La barre des tâches Windows est tranchée : rien, et c'est documenté.** Constat du
2026-09-05 sur **PySide6 6.11.1 / Qt 6.11.1** — aucun module `QtWinExtras` parmi les 64
livrés, donc pas de `QWinTaskbarProgress`. `ITaskbarList3` par `ctypes` aurait mis du COM
Windows-spécifique dans `gui/` pour un confort ; une dépendance tierce était exclue par le
plan. Le titre couvre le besoin, et c'est l'usage que Microsoft lui prête.
`tests/test_gui_bandeau.py` re-vérifie le constat à chaque exécution de la suite.

#### Le résultat NÉGATIF, et il compte autant que le reste

`tools/banc_progression.py` mesure le poids de chaque phase sur les `perf.log` du dépôt. La
règle du plan — « un écart min-max supérieur à un facteur 3 rend le poids inutilisable » —
**élimine six phases sur sept** :

| brique | phase | part médiane | n runs | écart | poids retenu |
|---|---|--:|--:|--:|---|
| manga | analyse (balayage A) | 32,4 % | 14 | ×1,6 | **32,4 %** |
| manga | terminologie | 4,9 % | 11 | ×18,8 | aucun |
| manga | traduction | 27,9 % | 14 | ×4,5 | aucun |
| manga | rendu | 34,2 % | 14 | ×3,2 | aucun |
| light novel | terminologie | 25,6 % | 11 | ×3,7 | aucun |
| light novel | traduction | 64,8 % | 11 | ×4,6 | aucun |
| light novel | mise en page | 9,6 % | 11 | ×3,8 | aucun |

Une phase pondérée sur sept ne fait pas un modèle pondéré. Les poids sont donc **livrés
désarmés** — `POIDS_MESURES` porte la mesure, `Phase.poids` vaut `None` partout — et le modèle
fonctionne en **compté** sur tous les runs du dépôt. Pas de repli sur des poids égaux : des
poids égaux inventés seraient un faux pourcentage avec l'aplomb d'un vrai.

#### Ce que le lot ne fait pas

Aucun ordre d'étape, aucune frontière d'arrêt, aucun checkpoint. Aucun paramètre de run, et ni
`--keep-awake` ni `--shutdown` exposés dans le lanceur graphique : c'est le `PLAN-33`.
`illustration/progression.py` n'est pas fusionné — le bandeau le lit par une façade
(`AtelierIllustration.etat_progression`). `progression_de_stage` et son test sont intacts : le
repli par expression régulière couvre toujours les étapes non instrumentées. Aucune dépendance
ajoutée, ni pour la barre des tâches, ni pour les notifications.

Tout est dans **`docs/mesures/progression-2026-09-05.md`**, qui reprend les onze critères du
plan un par un, y compris ce qui n'a pas été livré et pourquoi.

---

## [2.25.1] - 2026-09-04

### CORRECTIF — Deux garde-fous de dépôt tombaient sur une console Windows, et l'un ne tombait que quand il avait quelque chose à dire

> **Rien n'est périmé, et il n'y a rien à réarmer.** `config.yaml` ne change pas d'une ligne,
> son empreinte est inchangée. Aucun cache, aucun prompt, aucun seuil, aucun format de sortie,
> aucune ligne de `gui/`, `manga/`, `pipeline/` ni `core/`. Cinq outils de `tools/` et un
> fichier de tests.

`tools/verifier_disclosure.py` levait un `UnicodeEncodeError` sur une console Windows en
cp1252 — l'encodage par défaut d'un terminal non configuré, donc le cas courant. Il tombait
**après** avoir jugé les commits, en imprimant son verdict, sur le premier `⚠` de sa sortie :

```
UnicodeEncodeError: 'charmap' codec can't encode character '\u26a0'
```

⚠ **Et il ne tombait que lorsqu'il avait quelque chose à dire.** Le `⚠` n'apparaît dans sa
sortie que si un commit déclare « Revu et testé manuellement : non ». Un dépôt propre passait ;
une branche en attente de relecture plantait. Un garde-fou qui ne tombe qu'au moment où il
aurait servi n'est pas un garde-fou.

`tools/sonar_issues.py` tombait plus tôt encore : dès son `--help`, dont la docstring porte
deux `⚠`. Un outil dont on ne peut pas lire l'aide est un outil qu'on n'utilise pas.

#### Pourquoi quatre lignes répétées et pas le helper partagé

`core/cli.py:configurer_stdout()` fait exactement ce qu'il faut, et dix-neuf outils l'appellent
déjà. Mais **`core/cli.py` importe `yaml`**, et `.github/workflows/garde-fous.yml` lance ces
outils sur un Python nu — **aucun `pip install` dans tout le fichier**. L'appeler ici casserait
le job de CI qu'il est censé servir. Les quatre lignes sont donc répétées, la raison est écrite
à chaque site, et `tests/test_outils_sortie.py` les tient en phase.

Ce même fichier de tests pose la propriété qui explique la duplication — ces outils n'importent
**que la bibliothèque standard** — et vérifie que le job n'installe toujours rien. Le jour où
l'une des deux conditions changera, le test le dira ce jour-là plutôt que six mois après, dans
un `ModuleNotFoundError` au fond d'un log d'Actions.

#### Ce qui est corrigé, et ce qui est prévenu

| Outil | Avant | Après |
|---|---|---|
| `verifier_disclosure.py` | **tombe** sur son verdict | passe |
| `sonar_issues.py` | **tombe** sur `--help` | passe |
| `verifier_arbre.py` | passe | passe, et protégé |
| `verifier_livraison.py` | passe | passe, et protégé |
| `notes_de_version.py` | passe (stdout seul, reconfiguré trop tard) | passe, stdout **et** stderr, dès l'entrée de `main()` |

Les trois derniers ne tombaient pas : la seule chose qui les séparait de la panne était
qu'aucun `⚠` n'avait encore été tapé dans leurs chaînes. Ils tournent dans le même job sans
dépendance et écrivent dans le même résumé de CI.

⚠ `notes_de_version.py` **se reconfigurait déjà**, mais à la main, sur stdout seulement, et
juste avant son `print` final — son unique chemin d'erreur (`print(str(e), file=sys.stderr)`)
portait donc le même défaut. La reconfiguration remonte en tête de `main()`.

**18 tests neufs** (`tests/test_outils_sortie.py`), dont **7 échouent sur l'arbre d'avant le
correctif** — vérifié en remisant `tools/`. Ils lancent les vrais outils avec
`PYTHONIOENCODING=cp1252`, ce qui reproduit exactement la console qui les tuait.

---

## [2.25.0] - 2026-09-04

### MINEUR — Le démarrage ne charge rien : l'accueil, sept destinations, le tome à la demande

> **Rien n'est périmé, et il n'y a rien à réarmer.** `config.yaml` ne change pas d'une ligne,
> son empreinte est inchangée. Aucun cache, aucun checkpoint, aucun prompt, aucun format de
> sortie. La seule chose qui change de forme est `.angelith/interface.json`, le fichier de
> DISPOSITION de l'interface — et il est ignoré en bloc, comme il l'a toujours promis (voir
> « Ce qui change pour vous » plus bas).
>
> ⚠ **Ce lot n'ajoute aucune capacité de traitement.** Il déplace, il rend paresseux, il
> nomme. Un seul paramètre de run naît, `--format webtoon`, et il naît parce qu'une
> destination « Webtoon » qui ne le poserait pas serait un doublon du lanceur manga sous un
> autre nom.

#### 1. L'application ouvrait un tome que personne n'avait demandé

`gui/fenetre.py` appelait `_remplir_projets()` alors que les deux `QComboBox` de la barre haute
étaient déjà branchés : remplir la liste **déclenchait** `currentTextChanged`, donc
`_ouvrir_tome`, sur le premier projet par ordre alphabétique. Et « ouvrir » n'était pas une
figure de style — un `Tome` lu, un `Services` construit (l'objet qui porte les modèles chauds),
l'éditeur peuplé, et `FilDeLecture` lancé sur la composition des aperçus.

Mesuré le 2026-09-04 sur le corpus réel du dépôt (18 dossiers sous `sources/`, 16 sous
`build/`, dont 6 portent des planches manga), lancement chaud,
`QT_QPA_PLATFORM=offscreen`, médiane de 3 lancements :

| Grandeur | 2.24.1 | 2.25.0 |
|---|---:|---:|
| `QApplication()` → `show()` | **1,89 s** | **0,13 s** |
| dont ouverture du tome | 1,40 s | — |
| ouvertures de fichiers avant le premier pixel | 692 | **1** |
| tome ouvert sans qu'on le demande | *manga A* / Vol.1, 150 planches | **aucun** |
| `Services` construit | oui | **non** |
| glossaire YAML lu | 26,9 Ko | **non** |
| aperçus composés dans les 10 s | 11 | **0** |
| poids du cache d'aperçus | 62,4 Mo | **0 Mo** |
| pic de mémoire résidente | 311 Mo | **106 Mo** |

Le tome se rouvre en un clic — la carte « Reprendre » de l'accueil — et coûte alors exactement
ce qu'il coûtait : 4,0 s, 745 ouvertures, 11 aperçus, 62,4 Mo. **Le coût n'a pas été supprimé,
il a été rendu volontaire.**

Reproduire : `python tools/mesure_demarrage.py --attente 10 --markdown`.

#### 2. Une prémisse du dépôt était fausse, et la mesure l'a levée

Le lot 27 écrivait, dans `gui/fenetre.py` : « [le constructeur de `PanneauAtelier`] ne charge
aucun poids : le catalogue se calcule en lisant des champs et en listant des fichiers. Un
utilisateur qui n'ouvre jamais l'onglet ne paie rien. »

C'était vrai de l'intention, **faux du code** : `PanneauAtelier.__init__` appelle
`_remplir_projets` → `_sur_projet` → `illustration.orchestrateur._glossaire`, qui lit
`sources/<Projet>/glossaire.yaml`. Le relevé du 2026-09-04 le montre en une ligne : **26,9 Ko
de YAML lus au démarrage**, pour un onglet que personne n'avait ouvert. La phrase est
maintenant vraie, et `tests/test_gui_atelier.py` la garde.

#### 3. Sept destinations à la place de trois onglets

Une navigation latérale (`gui/navigation.py`), alimentée par une table en Python nu
(`gui/destinations.py`) sur le modèle exact de `gui/actions.py` :

| Demandé | Retenu | Motif |
|---|---|---|
| — | **Accueil** | il faut un endroit qui n'ouvre rien |
| LN | **Light novel** | déjà le libellé du dépôt ; un sigle en nav latérale ne se devine pas |
| MANGA | **Manga** | — |
| WEB | **Webtoon** | « WEB » se lit « site web » une fois sur deux |
| Génération d'Image | **Illustrations** | la destination porte un catalogue et une galerie |
| Gestion des Œuvres | **Œuvres** | une nav latérale nomme l'objet, pas l'activité |
| Modification | **Retouche** | « Modification » ne dit pas de quoi |
| — | **Réglages**, **Diagnostic** | en pied de pane, convention Fluent |

Sept destinations plus deux entrées de pied : la fourchette de la navigation latérale de
`NavigationView` (5 à 10), hors de celle des onglets. Les seuils de largeur sont ceux de
Fluent — 1008 px et 641 px — et la décision (`destinations.mode_pour_largeur`) se teste **sans
PySide6**, comme tout ce qui décide dans ce dépôt.

Chaque destination est une **fabrique** appelée au premier affichage. Un lancement qui reste
sur l'accueil ne construit aucun des trois panneaux (181 Ko de Python) que la 2.24.1
construisait d'office.

#### 4. Le webtoon est une destination, et ce n'est **pas** une brique

`core/version.py:ETAT_BRIQUES` n'en connaît pas, et il a raison : `run_manga.py
--format {manga,webtoon}` est un **format** du même orchestrateur. La destination « Webtoon »
est donc `gui/lanceur.py:PanneauLanceur` avec `format_planche="webtoon"` — la même classe, le
même `process_volume`, le même `tache_run`. Aucun code de traitement n'est dupliqué.

⚠ **Et la réserve mesurée du corpus de bandes est affichée en tête de la destination**, avant
le bouton : 15,1 à 17,0 % de fausses détections pour une cible de 5 %, et 5,9 bulles détectées
par bande là où 25 à 35 seraient attendues (`docs/mesures/webtoon-2026-08-26.md`, sur le seul
webtoon du corpus, qui est aussi son seul volume à source latine — les deux effets sont
confondus). Offrir le webtoon au même rang que le manga sans afficher cet écart promettrait
plus que ce qui est mesuré.

**Les réglages de bande sont remontés**, et deux drapeaux naissent pour eux :

| Réglage | Dans l'interface | En ligne de commande |
|---|---|---|
| hauteur des fenêtres de détection | modifiable, `0` = selon `config.yaml` | **`--fenetre-hauteur PX`** (nouveau) |
| recouvrement entre deux fenêtres | modifiable, `0` = selon `config.yaml` | **`--fenetre-recouvrement PX`** (nouveau) |
| sens de lecture | **affiché, non modifiable** | `manga.formats.webtoon.rendu.sens_lecture` |
| scan d'origine dans le PSD | **affiché, non modifiable** | `manga.formats.webtoon.rendu.psd_original` |

Le partage tient à une règle : **un panneau ne propose que ce que `run_manga.py` sait faire**,
sans quoi « un tome retouché ici se relance à l'identique avec `run_manga.py` » cesse d'être
vrai. Le sens de lecture reste hors de portée pour une autre raison : le changer sur un tome
déjà détecté fait reprendre **toutes** ses planches à la détection, ce qui est une invalidation
de cache — l'interdit n° 1 du dépôt. Les deux valeurs sont écrites dans le bloc du **format**,
au niveau le plus précis que le run va lire, et le récapitulatif d'avant-run les annonce.

⚠ **Aucun de ces deux réglages n'est mesuré sur le corpus de bandes.** Le défaut livré reste
`2160 / 900` ; l'interface ne suggère nulle part d'y toucher, et la réserve du webtoon reste
entière.

#### 5. L'accueil dit ce que la machine sait faire, sans jamais bloquer

Trois sondes (`gui/sondes.py`) : endpoint LLM joignable, poids de détection présents, Pandoc
trouvable. **Aucune ne s'exécute sur le fil d'affichage.** Elles partent après `show()`, dans
le fil de travail existant, avec un délai de 2 s, et l'accueil s'affiche complet avec les trois
marqueurs en « inconnu (en cours) ».

Mesuré avec un endpoint volontairement mort (`http://127.0.0.1:9/v1`) : **premier pixel à
0,10 s**, verdict « absent (ConnectTimeout) » huit secondes plus tard. Trois états et pas deux :
confondre « en cours » avec « injoignable » ferait dire à l'accueil quelque chose de faux
pendant une seconde à chaque démarrage.

Un genre de tâche naît pour elles, `GENRE_SONDE`, et `FilDeTravail.touche_tout()` l'exclut :
une tâche `planche=None` de genre ordinaire grise le bouton « Lancer », ce qui aurait posé un
verrou d'écriture pendant deux secondes, à chaque démarrage, pour un travail qui n'écrit rien.

#### 6. Ce qui change pour vous

- **`.angelith/interface.json` passe en version 2 et un fichier de version 1 est ignoré en
  bloc.** C'est le comportement que le module promet depuis le lot 18 — « une disposition
  perdue coûte trois clics, une disposition à moitié appliquée coûte une session » — et il n'y
  a **pas** de migration : `onglet: 0` deviendrait `destination: "retouche"`, c'est-à-dire un
  tome rouvert au démarrage, ce que le lot entier existe pour ne plus faire. Concrètement :
  taille de fenêtre, colonnes, filtre et réglages de run repartent des défauts **une fois**.
- **`force` et `dry_run` restent non persistés**, et le nettoyage descend d'un niveau : `runs`
  porte maintenant un sous-dictionnaire par destination de lancement, et un nettoyage resté à
  un niveau aurait laissé passer `runs["webtoon"]["force"]`.
- **`Ctrl+Tab` change de promesse sans changer de geste** : « onglet suivant » devient
  « destination suivante ». `Ctrl+1` … `Ctrl+6` atteignent les six destinations métier,
  `Ctrl+Maj+A` l'accueil, et un menu « Aller à » les rend découvrables.
- **Rien ne rouvre le dernier tome tout seul.** `dernier_projet` / `dernier_tome` sont toujours
  persistés ; ils alimentent la carte « Reprendre » de l'accueil, et il faut un clic.

#### 7. La fenêtre s'ouvre enfin à la taille demandée

`PanneauEditeur` cumule les minimums de ses trois colonnes. En 2.24.1, l'éditeur étant
construit au démarrage, la fenêtre entière portait ce minimum **dès le premier pixel** :
mesuré sur un écran réel de 2 560 × 1 440, l'application s'ouvrait à **2 016 × 981** et
`resize(1520, 960)` — le défaut de `gui/reglages.py`, et toute taille persistée plus petite —
était **silencieusement ignoré**.

Ce lot rend la fenêtre à sa taille demandée (**1 520 × 960** au lancement) parce que seule la
page affichée la contraint désormais. ⚠ **Le prix est réel** : ouvrir la Retouche élargit la
fenêtre à **2 214 px**, contre 2 016 px avant — les 198 px du pane de navigation. Et la source
n'est pas corrigée : elle est dans `gui/editeur.py`, que le plan écarte (§4). Le mode
« minimal » de la nav latérale (≤ 640 px) reste donc inatteignable en pratique, et c'est
écrit.

Tout est dans **`docs/mesures/coquille-2026-09-04.md`**, qui reprend les onze critères du plan
un par un, y compris les deux qui ne sont pas tenus.

---

## [2.24.1] - 2026-09-03

### CORRECTIF — `--liberer-vram` n'était jamais parti, et trois lignes de la sonde répondaient faux

> **Rien n'est périmé, et il n'y a rien à réarmer.** `config.yaml` ne change pas d'une ligne,
> son empreinte est inchangée. Aucun prompt, aucune image, aucun seuil, aucun format de sortie.
> `illustration.vram.decharger_image` vaut toujours `false` — et la mesure de ce correctif
> **ne soutient pas** de l'armer, ce qui est dit plus bas.

⚠ **Ce correctif vient d'une session de RELEVÉ sur le PC principal**, pas d'un lot de
développement : le bloc A de `docs/plans/A-EXECUTER-SUR-LE-PC-PRINCIPAL-28-30.md`, lancé le
2026-09-03 contre un vrai serveur ComfyUI pour la première fois. Tout ce qui suit a été trouvé
en **lançant** ce que les lots 28 et 30 avaient livré sans pouvoir l'exécuter.

### 1. `--liberer-vram` levait un `TypeError` avant le premier appel

`run_illustration.py` construisait `MoteurComfyUI(base_url=…, timeout=…)` sans son premier
argument **positionnel obligatoire**, `workflow` :

```
TypeError: MoteurComfyUI.__init__() missing 1 required positional argument: 'workflow'
```

La commande mourait après avoir affiché sa ligne « Avant : », avec ou sans `--repetitions`, sur
un serveur joignable, dans la configuration livrée. **Elle n'a jamais fonctionné** : `git log -L`
fait remonter la ligne à la 2.24.0, celle qui l'a créée.

Le moteur se construit désormais avec **`workflow=None`**, et c'est un choix : `decharger()` ne
touche qu'au transport — `POST /free` — et n'exécute aucun graphe. Passer le graphe configuré
ferait échouer « rends-moi la VRAM » parce qu'un fichier JSON est mal formé, ce qui est le pire
moment pour refuser.

⚠ **Le trou de couverture compte plus que la ligne.** `illustration/vram.py:mesurer_free` — la
logique qui compte, qui sonde entre deux appels et s'arrête au premier serveur mort — **était
testée**, et bien. Le **câblage** entre le drapeau de ligne de commande et elle ne l'était
nulle part : `grep -rn "liberer_vram" tests/` ne rendait rien. Un lot peut donc livrer un
mécanisme juste, testé et documenté, derrière une commande qui ne part pas. Deux tests neufs
ferment cette porte, et **tous deux échouent sur la 2.24.0**.

### 2. Le chiffre que ce correctif permet enfin — et pourquoi il ne ferme pas le critère 7

**0 panne sur 20 appels à `/free`**, ComfyUI 0.34.2, RX 7900 XT, ROCm 7.14, le 2026-09-03.

⚠ **Sur un serveur AU REPOS** : 20 315 Mio libres avant, 20 315 après — les vingt appels n'ont
rien libéré. Le mode d'échec relevé le 2026-08-29 est une violation d'accès **dans le
déchargement d'un modèle** ; un `/free` sans modèle à décharger ne traverse pas ce code. **Ce
chiffre ne mesure donc pas ce que le critère 7 du `PLAN-30` nomme**, et
`illustration.vram.decharger_image` **reste `false`**. Le seul chiffre en condition reste
« 1 panne sur 7 » du 2026-08-29. Détail dans `docs/mesures/canaux-2026-09-03.md` §13.

### 3. Trois lignes de `tools/comfy.py --sonde` répondent faux, et elles ne sont PAS corrigées ici

Relevées, publiées, non corrigées — un correctif de câblage n'est pas le lot qui refait une
sonde, et les trois demandent leur propre mesure :

| Elle affiche | Ce qui est vrai sur une installation Comfy Desktop |
|---|---|
| `Modèles : <installation>\models` | les modèles sont ailleurs ; le dossier annoncé ne contient que ses `put_*_files_here` |
| `extra_model_paths.yaml : absent` | un fichier de chemins existe, passé par `--extra-model-paths-config` |
| `installée (Desktop ou venv)` | `/system_stats` rend `deploy_environment`, que la sonde ne lit pas |

⚠ **Les deux premières se tiennent, et c'est ce qui les rend nuisibles** : qui suit la sonde
dépose un poids dans un dossier que le serveur ne lit pas. `docs/procedures/comfyui.md` §0 bis
porte le tableau ci-dessus, daté, pour qu'aucun lecteur ne s'y fasse prendre en attendant.

### 4. Ce que la session a fermé, et ce qu'elle laisse ouvert

| Lot | Avant | Après |
|---|---|---|
| 28 | 3 critères sur 9 non tenus | **critères 1, 3 et 5 tenus** ; 4 et 6 attendent une génération |
| 30 | 4 tenus, 2 à moitié, 3 non tenus | critère 4 **confirmé sur le vrai serveur** ; critère 7 toujours à moitié, mais pour la bonne raison |

Documents : `docs/mesures/comfy-visible-2026-09-02.md` §10 et
`docs/mesures/canaux-2026-09-03.md` §12–13, tous deux en **addendum daté** — les documents du
jour ne sont pas réécrits, c'est la règle du `00-CONTEXTE-AGENT.md` §5 bis.
`docs/procedures/comfyui.md` §0 est remesuré et daté du 2026-09-03, et son avertissement
« ce tableau n'a pas été remesuré » est levé.

---

## [2.24.0] - 2026-09-03

### MINEUR — Les canaux qui manquent : un canal instrumenté et non livré, deux refus nommés de plus, et un défaut d'élagage que rien ne pouvait voir

> **Rien n'est périmé, et il n'y a rien à réarmer.** `config.yaml` ne gagne **aucune clé** —
> son empreinte change, et **uniquement par des commentaires** ; le tableau du §8 de
> `docs/mesures/canaux-2026-09-03.md` compare les valeurs une par une. Aucun prompt livré ne
> change, aucune image, aucun seuil, aucun format de sortie. Le graphe par défaut est le même,
> `illustration.vram.decharger_image` vaut toujours `false`.

⚠ **AUCUN CANAL N'EST LIVRÉ, et c'est la conclusion du lot.** Le `PLAN-30` demandait de choisir
un canal **sur son apport mesuré** ; l'apport ne se mesure qu'avec le juge du `PLAN-29`, qui n'a
pas livré ses mesures. Sur les écarts **mesurés** — part d'aplats, densité de trait — aucun canal
de ce lot ne se justifie. Ce qui est livré est un **instrument** : un graphe candidat qui se
déclare comme tel, un axe de banc fermé par défaut, et un protocole de mesure de `/free`.
**Quatre critères sur neuf tenus, deux à moitié, trois non tenus** — tout est repris un par un
dans `docs/mesures/canaux-2026-09-03.md` §2.

### 1. Le graphe CANDIDAT — nouveau, désarmé, et il dit lui-même qu'il n'a jamais tourné

`illustration/workflows/qwen-image-edit-2511-controle.api.json` porte le canal **image de
contrôle** (`%image_controle%`), dérivé du graphe d'édition qui a tourné. Il n'est le défaut de
personne : `config.yaml` ne le désigne pas, et un test le garde.

**Le choix du canal ne s'est PAS fait sur l'apport** — il ne pouvait pas —, mais sur la **dette
d'installation**, qui est le second critère de l'étape 0.2 du plan :

| | image de contrôle | entités + masques (EliGen) |
|---|---|---|
| nœud | **intégré à ComfyUI** (`ModelPatchLoader`, `QwenImageDiffsynthControlnet`) | **tiers**, installé sur aucune machine du dépôt |
| poids | `qwen_image_canny_diffsynth_controlnet.safetensors`, **Apache-2.0 vérifiée à la source le 2026-09-03** | `Qwen-Image-EliGen-V2`, Apache-2.0 vérifiée le 2026-08-30 |
| entrée du canal | l'utilisateur fournit un trait | il faudrait **dessiner un masque** — un éditeur, donc un lot entier |

⚠ **L'empreinte SHA-256 du poids n'est PAS relevée** : le fichier n'a pas été téléchargé. Le
champ le dit au lieu de rester blanc, et le critère 2 n'est donc tenu qu'à moitié.

**Un graphe qui porte un bloc racine `_candidat`** voit ses refus « nœud absent » et « modèle
absent » **rétrogradés en réserves** par le validateur du lot 28. Sans quoi
`python tools/comfy.py --valider` (sans argument) serait passé en **rouge sur toute machine du
monde** — le faux avertissement que `core/config_schema.py` décrit en tête. Le constat n'est pas
effacé pour autant : il reste, avec la source du poids et sa licence datée, et c'est la liste de
courses de qui veut l'installer.

### 2. `CanalExige` — la réciproque du refus, pour le premier graphe qui ne dégrade pas

Jusqu'ici, un nœud dont le marqueur n'était pas substitué était **élagué**, et le graphe restait
exécutable. Un nœud de contrôle est **en série sur le chemin du modèle** : l'élaguer priverait le
`KSampler` de son modèle. Le graphe déclare donc `exige: [image_controle]`, et le refus arrive
**avant la première requête HTTP**, en nommant le champ à remplir.

⚠ **`CANAUX_EXIGES` est vide sur tous les moteurs livrés armés, et un test en fait une règle** :
un graphe qui exige un canal ne peut pas être le défaut de quiconque.

### 3. ⚠ Un défaut silencieux, corrigé : `%image_controle%` n'était pas élagable

L'élagage ne connaissait que les marqueurs **indexés** (`%reference_2%`, `%masque_3%`), parce
qu'aucun graphe du dépôt ne portait `%image_controle%` — le cas ne pouvait pas se produire. Sans
ce correctif, une requête sans image de contrôle aurait envoyé `LoadImage(image: "")` à ComfyUI,
qui répond par une erreur d'exécution **après** le chargement des poids. Même motif que les trois
défauts du lot 29 : un chemin qu'aucun test n'atteignait parce qu'aucun fichier livré ne
l'empruntait.

### 4. La copie non marquée est TRANCHÉE — et le conseil du dépôt était faux

Le `README` des workflows conseillait depuis la 2.16.0 de remplacer `SaveImage` par
`SaveImageWebsocket`. ⚠ **Ce client ne sait mécaniquement pas lire ce nœud** : il récupère
l'image par `/history` puis `/view`, et `SaveImageWebsocket` ne publie rien dans l'historique. Un
graphe qui le porte occuperait la carte plusieurs minutes puis échouerait sur « n'a produit
aucune image ». **Le validateur le refuse désormais** (`sortie_websocket`), et le README porte un
bloc daté qui **lève** son ancien conseil au lieu de le réécrire.

**Sixième vérification de `--valider`** : où atterrit la copie que ComfyUI écrit en plus de celle
qu'Angelith marque.

| Nœud | La copie | Verdict |
|---|---|---|
| `SaveImage` | `output/`, permanente | **réserve** `copie_non_marquee` — l'état livré, assumé, et désormais dit au moment de valider |
| `PreviewImage` | `temp/`, vidée au redémarrage de ComfyUI | ✓ rien à signaler — le client transmet déjà le `type` de l'historique à `/view` |
| aucun nœud de sortie | — | **refus** — ComfyUI exécuterait sans rien publier |

⚠ **Aucun graphe livré ne bascule sur `PreviewImage`** : cette ligne décrit une lecture du code,
pas un relevé, et changer où atterrit une copie que des utilisateurs veulent garder se mesure
d'abord.

### 5. `/free` : le protocole est livré, le chiffre ne l'est pas

```powershell
python run_illustration.py --liberer-vram                    # rendre la carte, une fois
python run_illustration.py --liberer-vram --repetitions 20   # le relevé du PLAN-30 L30.4
```

⚠ **Le mode d'échec n'est pas celui qu'on croit** : `POST /free` ne rend pas d'erreur, il **tue
le serveur**. Une boucle de vingt appels qui ne sonderait pas entre deux compterait dix-neuf
succès imaginaires après le premier plantage. Le protocole sonde après chaque appel, s'arrête au
premier serveur mort, **dit à quel rang**, et rappelle que les dénominateurs s'additionnent.

⚠ **Il n'arme rien et ne relance jamais ComfyUI.** Le chiffre en vigueur reste **1 sur 7**, du
2026-08-29 — et sept n'est pas un dénominateur. `decharger_image` reste donc `false`, ce qui est
la bonne conséquence de l'absence de chiffre.

### 6. L'axe `canal` du banc — L30.2, fermé par défaut

```powershell
python tools/banc_identite.py "<Projet>" <Tome> --personnage "<nom>" --balayage --controle <trait.png> --markdown
```

Un **seul** point d'axe, symétrique de l'axe `decor` du lot 29 : le plan ne demande pas de
balayer la force du canal, il demande de le comparer à son absence, sur les mêmes descripteurs et
le même juge. Sans `--controle`, le balayage rend exactement les cinq configurations d'avant sous
exactement les mêmes noms — deux séries mesurées à six mois d'écart restent comparables fichier
par fichier. Le fichier est vérifié **avant** tout chargement de modèle, et `--devis` compte
l'image de plus.

### Fichiers touchés

- **neufs** : `illustration/workflows/qwen-image-edit-2511-controle.api.json`,
  `tests/test_illustration_canaux.py` (27 tests), `docs/mesures/canaux-2026-09-03.md` ;
- `illustration/comfyui.py`, `illustration/moteur.py`, `illustration/validation.py`,
  `illustration/vram.py`, `run_illustration.py`, `tools/banc_identite.py` ;
- `config.yaml` (**commentaires seulement**), `illustration/workflows/README.md`,
  `docs/procedures/comfyui.md`, `docs/COMMANDES.fr.md` ;
- **aucun fichier de prompt n'est touché.**

## [2.23.0] - 2026-09-03

### MINEUR — Le juge et le corpus : le protocole en aveugle est enfin outillé, trois défauts silencieux sont corrigés, et sept critères sur neuf ne sont pas tenus

> **Rien n'est périmé, et il n'y a rien à réarmer.** Ce lot n'ajoute **aucune clé** à
> `config.yaml` — son empreinte est inchangée depuis la 2.21.0 —, ne change **aucun prompt
> livré**, aucune image, aucun seuil, aucun format de sortie. `requete.yaml` gagne un champ
> `decor` dont le défaut reproduit le comportement d'avant **mot pour mot**, et un test le
> vérifie ; un fichier validé d'avant le lot ne redemande pas de validation.

⚠ **Ce lot livre principalement un résultat négatif documenté, et c'est ce que le plan
autorisait** : « ce lot peut se conclure par "le juge automatique est inutilisable et on s'en
passe" : c'est un résultat, et il se publie comme tel ». Ici le constat est en amont — **on ne
sait toujours pas**, et on sait maintenant précisément ce qu'il faut pour savoir. Les sept
commandes qui ferment les sept critères sont au §10 de
`docs/mesures/identite-2026-09-03.md`, et **aucune ne demande d'écrire du code**.

### 1. ⚠ Sept critères sur neuf ne sont pas tenus, et TROIS ressources manquaient, pas une

Le plan prévenait qu'il fallait le PC principal. La session a tourné sur le secondaire — mais
contrairement au lot 28, ce n'est pas seulement le GPU qui manquait :

| Ce qui manque | Relevé | Ce que ça ferme |
|---|---|---|
| **la bible** | `find sources -name "bible*"` → **0 fichier** sur 17 projets | critères 1, 2, 6 — aucune référence à recadrer, re-rôler ou compter |
| **les poids du juge** | `illustration_models/` ne porte que son README ; `onnxruntime` est installé, lui | critère 2 |
| **ComfyUI et la carte** | `WinError 10061`, carte Intel — comme au lot 28 | critères 3, 5, 6, 7 |

⚠ **La deuxième ligne est la plus coûteuse, et le plan ne l'avait pas prévue.** L'étape 0.1 —
« réétalonnez le juge inchangé » — est la seule du lot qui **n'avait pas besoin de GPU** :
DINOv2 tourne sur CPU par `onnxruntime`. Elle aurait pu se faire ici. Elle ne l'a pas pu,
faute des **poids** — que le dépôt ne télécharge pas, par choix. **Enseignement pour les
plans suivants** : « se lance sur le principal » est une condition trop grossière.

### 2. Le protocole en aveugle est OUTILLÉ — et il porte ses trois règles dans le code

```powershell
python tools/juge_humain.py "roman S" --paires 20 --seuil 14   # présente, enregistre
python tools/juge_humain.py "roman S" --rapport --markdown     # l'ACCORD humain/automatique
```

1. **le seuil est écrit dans le protocole à sa création**, et `--rapport` le lit **de là**. Il
   n'existe **pas** d'option `--seuil` à la lecture : un seuil qu'on peut passer après avoir
   vu les résultats ne mesure rien ;
2. **rien ne trahit la configuration** — copies nommées `paire-07-A.png`, écrites dans un
   ordre tiré au sort, correspondance dans un `protocole.json` à n'ouvrir qu'après ;
3. **les réponses sont horodatées, en ajout seul.** Se reprendre ajoute une ligne ; le journal
   garde les deux.

⚠ **Un test a fait changer une ligne, et c'est le genre de défaut que la relecture n'attrape
pas.** Les copies passaient par `shutil.copy2`, qui recopie les métadonnées — **date de
modification comprise**. Les copies héritaient donc de la date de l'image d'origine : un
dossier trié par date rendait l'ordre du balayage, c'est-à-dire l'ordre des configurations.
Mélanger l'ordre d'écriture ne servait à rien tant que la date suivait le fichier. C'est
exactement la fuite que la règle 2 du plan nomme, réintroduite par l'appel le plus naturel de
la bibliothèque standard.

⚠ **Le produit de cet outil n'est pas un verdict, c'est un ÉTALON.** Personne ne sait si le
0,68 de séparation du lot 25 est un mauvais score, parce que personne n'a mesuré ce qu'un
humain fait sur les mêmes paires. C'est l'accord humain/automatique qui le dira.

### 3. Le corpus se compte, et l'écart entre les deux comptes est le sujet du lot

```powershell
python tools/bible.py "roman S" --corpus                    # le tableau 0 / 1 / 2 / ≥3
python tools/bible.py "roman S" --revue --role identite     # couvertures en dernier, cadre proposé
```

Le tableau s'affiche **avant et après chaque revue**, en deux comptes : toutes les références
d'identité validées, puis les mêmes **sans les couvertures**. Publier le seul compte de gauche
aurait dit « corpus prêt » au lot 25, dont les trois références validées étaient trois
couvertures — dont deux le même dessin.

⚠ La règle « les couvertures en dernier » existait depuis le lot 26, mais **seulement au
moment de générer**. Elle arrive alors trop tard : c'est à la revue que le corpus se constitue.

### 4. Le rectangle proposé, mesuré sur 402 images — et il ne fait pas ce qu'on espérait

`core/illustrations.py:boite_d_encre` mesure **où est l'encre** — même gradient que
`densite_trait`, fermé sur 98 % de la masse pour laisser dehors poussières et liserés de
reliure. Aucune détection de visage, aucun OpenCV (interdit n° 4).

| | valeur |
|---|---:|
| images mesurées, corpus `build/` entier | **402** |
| part de page couverte, **médiane** | **0,7747** |
| boîtes couvrant moins de 50 % de la page | **10 (2,5 %)** |
| moins de 80 % | 231 (57,5 %) |

⚠ **Résultat négatif, et utile** : la boîte retire les **marges**, pas la page. Elle ne
localise **pas** un personnage, et le `motif` rendu à l'écran dit l'hypothèse en toutes
lettres — « le haut de l'encre est la tête, à corriger à l'œil ». Le recadrage assisté est une
**assistance**, pas une automatisation : la demi-journée humaine que le plan chiffre n'est pas
réductible par ce mécanisme.

**Et un fait nouveau, mesuré sans bible ni carte** : les deux tomes du corpus portent
**31 illustrations exploitables hors couverture** pour un besoin de 24 références (8 × 3). La
ressource n'est pas le blocage — **l'œil humain l'est**.

### 5. ⚠ Trois défauts silencieux du dépôt, corrigés

**Le champ de recadrage était ÉCRIT sous un nom et LU sous un autre.** `core/bible_llm.py`
écrivait `recadrage: []` depuis la 2.14.0 ; `illustration/identite.py` lisait `cadre`. Le
champ que le moteur lit **n'a jamais pu être rempli** par la chaîne d'outils — ce qui explique
en partie pourquoi l'axe « nature du recadrage » du `PLAN-25` est resté non mesuré **deux lots
de suite**, avec pour raison publiée « le champ reste vide sur les 10 références du corpus
réel ». Il restait vide parce que rien ne pouvait l'écrire. `cadre` devient le nom canonique,
`recadrage` est relu comme alias, et un cadre invalide est désormais **signalé** au lieu de
faire retomber la référence sur la page entière en silence.

**`tools/banc_identite.py --balayage` levait un `AttributeError` depuis la 2.18.0.** La
2.18.0 a renommé `requete.depuis_bible` en `depuis_oeuvre` sans que cet appelant suive.
⚠ Aucun test ne pouvait le voir : `--balayage` charge 12,8 Go et écrit des images, donc il
n'est exercé sur aucune machine sans carte. Corrigé **et découpé** — calculer le prompt d'un
personnage n'a jamais eu besoin d'un GPU, et c'est désormais testé sans.

**Et un TROISIÈME, de la même famille, trouvé en corrigeant le second.** La 2.19.0
(`5531029`) a rangé les illustrations par **œuvre** et non plus par tome :
`orchestrateur.dossier` est passé de trois arguments à deux. **Trois appelants n'ont pas
suivi** — `tools/banc_identite.py` une fois, `tools/banc_prompt.py` deux fois — et tous
levaient un `TypeError` au premier appel. `--balayage` cumulait donc **deux** pannes
indépendantes. Un test lit désormais la signature réelle et refuse tout appel de trop dans
`tools/` : il aurait échoué avant ce lot.

### 6. Le levier du décor, livré DÉSARMÉ

La part d'aplats de l'image générée vaut **0,6300** contre **0,3669** pour le tome — le seul
descripteur qui ait EMPIRÉ pendant que la moyenne progressait, et le plan en nomme la cause
probable : « sur fond neutre » **demande** une grande surface d'une seule teinte.

Quatre variantes sont livrées (`neutre`, `trame`, `sommaire`, `aucun`), avec un champ dans
`requete.yaml`, le décor archivé dans le sidecar, et un axe de balayage
`--decors neutre,trame,aucun` **fermé par défaut**.

⚠ **`DECOR_DEFAUT` reste `neutre`, et c'est le point.** Aucune mesure ne désigne un
remplaçant, et le dépôt ne change pas un prompt sur une hypothèse — même règle que
`manga.onomatopees.effacement.mode` au lot 22. Une variante inconnue **lève** au lieu de
retomber en silence sur `neutre`, et elle est validée **avant** le chargement des poids.

⚠ **Et l'axe fermé ne renomme aucun fichier.** Un balayage lancé sans `--decors` écrit
exactement les mêmes noms qu'avant le lot 29 (`force-r2-p6-g1`) : deux séries mesurées à six
mois d'écart restent comparables fichier par fichier, et un document de mesure publié ne
renvoie pas à des noms qui n'existent plus.

### 7. Le coût du lot, publié avant de lancer

```powershell
python tools/banc_identite.py "roman S" --devis
```

| Ce qu'on lance | images | **coût GPU** |
|---|---:|---:|
| ce que le plan demande — 8 × 10 en **édition** | 80 | **5 h 11 min** |
| les mêmes en texte-vers-image | 80 | 2 h 18 min |
| le balayage livré, 8 × 5 configurations | 40 | 2 h 35 min |

Le plan annonçait « environ 5 h 12 » ; le calcul du dépôt retombe sur 5 h 11 min, et un test
le tient. ⚠ **Le dénominateur du coût d'édition vaut UN** — 233,7 s est un essai de sonde, pas
la médiane de quatre images qu'est 103,7 s ; entre le meilleur et le pire relevé du dépôt le
rapport est de 14,7. ⚠ Et le devis **ne compte que le GPU** : il ignore la demi-journée de
relecture humaine, qui est le vrai poste dimensionnant.

### 8. L29.3 n'est PAS ouverte, et le plan demandait qu'on écrive pourquoi

Pas parce que l'étape 0.1 a suffi : parce qu'elle **n'a pas pu être tentée**. Ouvrir un
chantier de métrique avant d'avoir corrigé le corpus serait ce que le plan interdit en tête —
« optimiser un instrument contre un étalon faux ». Aucun budget d'abandon n'a été écrit,
aucune piste essayée, aucune heure dépensée.

### Fichiers

- **neufs** : `illustration/aveugle.py`, `tools/juge_humain.py`,
  `tests/test_illustration_aveugle.py`, `tests/test_illustration_corpus.py`,
  `tests/test_illustration_decor.py`, `tests/test_tools_juge_humain.py`,
  `tests/test_tools_banc_identite.py`, `docs/mesures/identite-2026-09-03.md` ;
- **modifiés** : `core/bible.py` (le compte du corpus, l'alias de cadre, la validation),
  `core/bible_llm.py` (le bon nom de champ), `core/illustrations.py` (`boite_d_encre`,
  `cadre_propose`), `illustration/identite.py` (lecture des deux noms),
  `illustration/gabarits/` + `portrait.yaml` (les variantes de décor),
  `illustration/prompt.py`, `illustration/requete.py`, `illustration/orchestrateur.py` (le
  décor dans le sidecar), `illustration/attente.py` (`devis`), `tools/bible.py`
  (`--corpus`, `--role`, recadrage assisté), `tools/banc_identite.py` (`--devis`,
  `--decors`, et le `--balayage` réparé) ;
- **aucun fichier de prompt de `langues/` touché.** Aucune dépendance ajoutée.

**3 969 tests collectés** (2026-09-03, toutes dépendances optionnelles), **+97**, tous hors
marqueur — donc tous exécutés en CI, sans serveur, sans GPU, sans encodeur et sans bible.

---

## [2.22.0] - 2026-09-02

### MINEUR — Voir ce que le projet envoie à ComfyUI : une sonde, un validateur, le graphe archivé, et une phrase fausse depuis six versions

> **Rien n'est périmé, et il n'y a rien à réarmer.** Ce lot n'ajoute **aucune clé** à
> `config.yaml` — son empreinte est inchangée — ne change aucune image, aucun prompt, aucun
> seuil, aucun format de sortie. Il ajoute un outil, des refus **avant** le GPU, et un fichier
> de trace à côté de chaque image produite.
>
> ⚠ **Le seul changement du chemin nominal est un refus de plus**, avant la bascule VRAM, sur
> un graphe que ComfyUI aurait de toute façon rejeté — ou qui aurait produit une image brûlée
> sans le dire. Le `config.yaml` livré ne déclenche aucun de ces refus, c'est vérifié.

Le problème, dit par l'utilisateur : « la construction et le déploiement du système d'image se
fait au travers du projet sans que je puisse avoir une réelle vision sur ce dernier ». Un
pipeline qu'on ne peut pas inspecter ne peut pas être débogué, et une mesure qu'on ne peut pas
rejouer à la main n'est pas une mesure.

### 1. `tools/comfy.py` — cinq sous-commandes, et **aucune ne génère**

```powershell
python tools/comfy.py --sonde        # version, variante, dossiers, nœuds tiers, VRAM, listes de modèles
python tools/comfy.py --valider      # avant le GPU : format, nœuds, modèles, canaux, pas/guidage
python tools/comfy.py --graphe <requete.yaml>   # le graphe SUBSTITUÉ, écrit sur disque, non envoyé
python tools/comfy.py --diff a.json b.json      # ce qui change, champ par champ
python tools/comfy.py --journal      # le dernier run : temps, VRAM, lignes du serveur archivées
```

⚠ **« Ne peut pas générer » est une propriété comptée, pas relue.** L'outil n'appelle que
`GET /system_stats`, `GET /object_info` et `GET /internal/logs/raw` ;
`test_aucune_sous_commande_n_envoie_de_generation` fait tourner chaque sous-commande contre un
serveur factice et vérifie **zéro `POST`**. Générer reste le travail de `run_illustration.py`,
qui porte la porte humaine et le marquage : un second chemin capable d'envoyer un `/prompt`
serait une seconde porte, non gardée.

⚠ **Le sondage est EXTRAIT, pas dupliqué.** `tools/banc_prompt.py` savait déjà interroger
`/object_info` — c'est lui qui a relevé les 907 nœuds du 2026-08-30. Le code vit désormais dans
`illustration/sonde.py`, et le banc en est devenu un appelant parmi deux. Un second sondeur
aurait divergé du premier, et `core/config_schema.py` dit en tête ce que ça coûte : « une liste
recopiée à la main dérive, et une référence qui dérive produit de **faux** avertissements — ce
qui est pire que pas de vérification du tout ».

### 2. Cinq vérifications avant le GPU, dont une que ComfyUI ne signale jamais

| # | Vérification | Le cas mesuré où elle aurait servi |
|---|---|---|
| 1 | format API, pas format écran | le client le disait déjà — **au moment de générer**, donc après le déchargement du LLM |
| 2 | chaque `class_type` existe sur **ce** serveur | `UnetLoaderGGUF` n'existe que si `ComfyUI-GGUF` est installé |
| 3 | chaque valeur de liste déroulante est dans la liste | un graphe versionné stocke le **nom** d'un modèle, pas un identifiant : le renommer casse tout |
| 4 | les canaux que le graphe déclare | un seul des trois graphes du dépôt porte `%reference_1%` |
| 5 | cohérence **pas / guidage** avec la LoRA | `cfg 4` + LoRA Lightning = images brûlées, **et ComfyUI n'en dit rien** |

`run_illustration.py --check` fait tourner ces cinq contrôles, et la **phase image** aussi —
juste avant la bascule VRAM, au même endroit que la vérification des canaux. Un modèle renommé
coûtait jusqu'ici une carte rendue et 12,84 Go chargés pour être découvert. Chaque refus porte
sa **correction**, pas seulement son constat.

⚠ **Un serveur éteint donne « NON FAIT », jamais « passé ».** Les contrôles 2 et 3 ont besoin du
serveur ; les contrôles 1, 4 et 5 marchent hors ligne. Un validateur qui refuserait un nœud
parce que ComfyUI n'est pas lancé refuserait les trois graphes du dépôt à chaque diagnostic —
c'est le faux avertissement qu'on cherche à éviter, pas à produire.

⚠ **Le contrôle de VRAM compte au crédit ce que PyTorch a déjà réservé**, et pas seulement le
libre. Sans ça il aurait crié à chaque seconde génération : après un run, ComfyUI garde
12 083 Mio résidents, le libre tombe sous le pic de 14 417 Mio — alors que relancer le même
graphe ne recharge rien.

### 3. Le graphe part avec l'image, et les trois lignes qui décident avec lui

Chaque image produite par le moteur ComfyUI garde désormais, à côté d'elle :

- **`<image>.png.graphe.json`** — le graphe **réellement envoyé**, marqueurs substitués, nœuds
  élagués. Il se glisse-dépose dans ComfyUI, qui recharge le graphe exact ;
- dans son sidecar, **`journal_serveur`** : `loaded completely` / `loaded partially`,
  `lowvram patches: N`, `Prompt executed in …`.

⚠ **C'est la différence entre une trace et un souvenir.** Un run qui a produit une image étrange
ne laissait aucun moyen de savoir si le transformeur avait été rogné — donc si l'image vient du
régime mesuré ou de l'autre, celui à 64,3 s/pas. La console du serveur, elle, s'efface au
redémarrage.

⚠ **Le graphe ne va PAS dans le PNG.** Le bloc `tEXt` porte l'identité de l'image, pas un JSON
de plusieurs kilo-octets ; le sidecar porte la **référence** du fichier et son empreinte
SHA-256. Un manifeste où le graphe serait recopié deviendrait illisible à l'œil — or c'est le
fichier qu'un humain ouvre. Le graphe suit l'image quand on la garde, la jette ou la purge.

### 4. Une phrase fausse depuis six versions, et la règle qu'elle impose

`illustration/comfyui.py` affirmait, de la 2.15.0 à la 2.21.0 : « ce client **n'a jamais tourné
contre un vrai serveur ComfyUI** ». C'était vrai le jour où c'était écrit. C'était **faux depuis
la 2.16.0** — 25 générations, 0 échec d'exécution, le 2026-08-29 — et personne ne l'a vu parce
que la phrase ne portait pas sa date. Un lecteur qui la croyait renonçait à un moteur qui
marchait.

Le relevé complet est publié : **50 correspondances, 25 fichiers, 7 vraies affirmations d'état,
1 périmée.** Les quatre qui étaient vraies mais muettes portent maintenant leur date
(`illustration/identite.py`, `scene.py`, `selection.py`, `core/illustrations.py`). Et la règle
est écrite au §5 bis de `docs/plans/00-CONTEXTE-AGENT.md` :

> Toute affirmation d'**état** dans le code porte sa **date** et le document qui l'établit. Un
> commentaire qui vieillit sans le dire est un faux avertissement, et un faux avertissement
> cesse d'être lu.

C'est le corollaire exact de la règle des chiffres du dépôt, et il a la même cause.

### 5. ⚠ Trois critères du plan sur neuf ne sont pas tenus, et c'est la MACHINE

La session qui livre ce lot a tourné sur le **PC secondaire** : pas de ComfyUI, pas de
RX 7900 XT — `WinError 10061` et une carte Intel. Le plan prévenait que ce lot devait se lancer
sur le principal.

- **critère 1** — la variante d'installation, les dossiers de modèles et les nœuds tiers ne sont
  **pas relevés**. L'outil qui les relève en une commande est livré et testé ;
- **critère 4** — le `.api.json` de `--graphe` n'a **pas** été rechargé dans ComfyUI, et aucune
  image n'a été reproduite à la main ;
- **critère 3, moitié** — les contrôles « nœud absent » et « modèle absent » n'ont été exercés
  que contre un `/object_info` **factice**, jamais contre le vrai serveur.

`docs/mesures/comfy-visible-2026-09-02.md` reprend les neuf critères un par un, publie ce que la
mesure ne dit pas, et donne les six commandes qui ferment ces trois cases sur le principal.
Aucune ne demande d'écrire du code.

### Fichiers

- **neufs** : `illustration/sonde.py`, `illustration/validation.py`, `tools/comfy.py`,
  `tests/test_illustration_sonde.py`, `tests/test_illustration_validation.py`,
  `tests/test_tools_comfy.py`, `docs/mesures/comfy-visible-2026-09-02.md` ;
- **modifiés** : `illustration/comfyui.py` (graphe public, substitution sans téléversement,
  trace, docstring datée), `illustration/marquage.py` (le graphe à côté de l'image),
  `illustration/galerie.py` (il suit l'image), `illustration/orchestrateur.py` (refus avant la
  bascule), `run_illustration.py` (`--check` valide), `tools/banc_prompt.py` (il appelle la
  sonde), `docs/procedures/comfyui.md`, `docs/plans/00-CONTEXTE-AGENT.md`,
  `docs/COMMANDES.fr.md`, `docs/chiffres-de-reference.md` ;
- **aucun fichier de prompt touché.** Aucune dépendance ajoutée.

**3 872 tests collectés** (2026-09-02, toutes dépendances optionnelles), **+61**, tous hors
marqueur — donc tous exécutés en CI, **sans serveur ComfyUI**.

---

## [2.21.0] - 2026-09-02

### MINEUR — L'atelier dans l'interface, la porte que les deux interfaces franchissent, et ce qui sort du dossier

> **Rien n'est périmé pour qui n'a rien armé.** `run.py`, `run_manga.py` et `run_ocr.py` sont
> iso-comportement : `illustration.actif` vaut `false`, `illustration.inserer_dans_sorties`
> vaut `false`, et le pipeline light novel **ne lit même pas** le dossier des images retenues
> tant que la seconde clé n'est pas armée.
>
> ⚠ **SAUF si tu avais tiré la 2.20.0 et que tu t'en servais telle quelle.** Le `config.yaml`
> publié par ce commit-là armait la brique d'illustration : `actif: true`, `moteur: comfyui`,
> `identite.actif: true`, `prompt.llm.actif: true`, plus un workflow d'édition et un timeout à
> 1 200 s. Ce sont six valeurs de travail d'une machine entrées par mégarde dans un lot qui
> parlait de **polices de manga**. Elles sont **remises à ce qu'elles étaient en 2.19.1**. Si
> tu utilisais la brique via le fichier livré, réarme les clés que tu veux — le bloc
> `illustration:` de `config.yaml` porte le chiffre qui justifie chacune.

### 1. L'écran de relecture, et c'est le cœur du lot — pas la galerie

Une interface qui enchaînerait les deux phases d'un seul bouton supprimerait la porte humaine,
donc la propriété qui rend cette brique défendable. L'onglet **« Atelier »**, à côté de
« Planches » et « Runs », a donc **deux pages**, et on ne va de la première à la seconde qu'en
passant par la phase 1.

- **`illustration/relecture.py`** construit ce qu'il faut montrer : le prompt éditable avec
  son original **restaurable** (une correction doit s'annuler sans relancer des minutes de
  LLM), le prompt négatif avec **le motif de chaque terme** tiré du gabarit, les vignettes en
  **deux groupes visuellement distincts** — identité et style —, chacune avec son motif, et
  **la source de chaque attribut** du prompt.
- **Ce qui est anormal est dit AVANT le clic** : un attribut sans citation, une référence
  introuvable ou **ambiguë**, un terme négatif absent du gabarit, toutes les références
  décochées. Le critère du plan est explicite : « aucun message d'erreur n'apparaît **après**
  le clic ».
- **Les canaux structurés se désarment, ils ne s'éditent pas.** Un éditeur de masque est un
  lot à lui seul, et il n'est pas celui-ci.
- **La porte est un objet, et les deux interfaces la franchissent.** `relecture.Porte` est le
  seul écrivain de `valide: true` ; l'atelier console, qui l'écrivait lui-même, passe
  désormais par elle. Deux portes, c'est une porte de moins qu'on croit avoir.
- **Aucun « générer directement » n'est ajouté** : ni bouton, ni raccourci, ni clé de
  configuration, pas même pour rejouer une requête déjà validée — le rejeu passe par
  `--rejouer` sur un sidecar, donc sur un prompt validé une fois.

**Deux tests tiennent cette propriété, et il en faut deux.** À l'exécution,
`Porte.laissez_passer()` lève tant que l'écran n'a pas été franchi. Statiquement,
`tests/test_illustration_relecture.py` lit `gui/atelier.py` avec `ast` et refuse qu'une
fonction nomme `phase_image` sans nommer `laissez_passer` : le premier ne verrait pas un
second chemin ajouté demain, le second ne verrait pas un appel par `getattr`.

### 2. La forme de l'atelier est imposée par un chiffre, pas par un goût

`illustration/attente.py` porte le tableau de l'étape 0.1 du plan et les trois relevés publiés
par les lots 24 à 26, **avec leurs dénominateurs** : 103,7 s par image en médiane (n = 4,
RX 7900 XT), 857,7 s au premier usage réel, 1 524 s au pire cas. Médiane pondérée 103,7 s,
soit **1,7× le seuil du haut du tableau**. La tranche est donc « run par lot : on lance, on
revient », et l'interface la sert :

- elle **annonce la fourchette mesurée avant** d'engager le GPU ;
- sa barre reste **indéterminée** tant qu'aucune image n'est terminée — le coût varie d'un
  facteur **14,7** sur cette machine, une barre qui annoncerait « 42 % » se tromperait d'un
  facteur dix un jour sur deux ;
- elle compte en **images terminées**, jamais en pas de débruitage.

**Et un résultat qui contredit une prémisse du plan** : L27.2 prévoyait que la bascule de
modèle puisse être « le poste le plus long ». Elle ne l'est pas — **2,03 s contre 103,7 s,
soit 2 %**. La progression la distingue quand même (`préparation (LLM)` / `bascule de modèle`
/ `génération (image)`), parce qu'une barre immobile qui ne dit pas ce qui occupe la carte est
un défaut d'information.

### 3. La bascule VRAM se ferme sur TOUS les chemins de sortie, et le LLM revient — parfois

Deux trous, tous deux nommés par L27.2 :

- **la fermeture n'avait pas lieu sur erreur ni sur annulation.** `_rendre_la_vram` vivait
  *après* le bloc de génération : une exception, un `Ctrl+C` ou un clic sur « Annuler »
  sautaient par-dessus, et 12 Go de transformeur restaient sur la carte. Le coût est mesuré et
  il est chez le pilote : un abandon sale a fait chuter le débit de **25 à 18 tok/s** ;
- **le LLM ne revenait jamais.** `illustration.vram.recharger_llm` le fait maintenant.

⚠ **Mais il ne revient que si la carte est réellement libre.** Appliquer « le LLM revient » à
la lettre serait un défaut : recharger ~17 Go pendant que ComfyUI tient ses ~12 Go est
exactement le scénario que l'architecture refuse. Le rechargement est donc conditionné à
`vram.decharger_image`, désarmé par défaut — **donc rien ne change sur la configuration
livrée**, et quand le rechargement n'a pas lieu, la brique le **dit** au lieu de le taire.

L'annulation, elle, a lieu **entre deux images, jamais au milieu de l'une**, et
`vram.Bascule.fermer` est **idempotente** : un second clic n'envoie pas un second `/free` à un
serveur dont un appel sur sept a déjà fait segfauter ComfyUI.

### 4. Garder, jeter, et ne rien perdre

- **Garder DÉPLACE** l'image *et son sidecar* vers `sources/<Projet>/illustrations/`, qui
  survit à un `rm -r build/` — que le dépôt recommande lui-même après un MAJEUR. Une image
  produite en 103,7 s de GPU n'est pas régénérable : la même graine sur une autre révision ne
  rend pas la même image, et le lot 24 l'avait déjà écrit.
- **Rien n'est jamais réécrit** : un nom qui existe obtient un suffixe. **Jeter ne supprime
  pas** : un rejet est une donnée dont le lot 25 a besoin. La purge existe, c'est un geste
  séparé, et elle annonce ce qu'elle détruit.
- **Une image gardée sans son manifeste est REFUSÉE** : elle ne pourrait plus dire qui a
  validé son prompt ni depuis quelles références, c'est-à-dire ce qui la rend défendable.

**Et le point le plus important du lot** : une image produite **ne peut pas** devenir la
référence d'une génération suivante. Reboucler la sortie dans l'entrée fait dériver le
personnage à chaque tour, et la dérive est invisible image par image. Trois mécanismes
indépendants l'empêchent — la clé `images_generees[]` distincte de `references[]` dans
`bible.yaml`, le refus par dossier, le refus par marquage AI Act — et le test fait
**l'aller-retour complet** : générer, garder, inscrire, relire, la liste des candidates est
inchangée.

### 5. L'insertion dans les sorties du light novel, opt-in et étiquetée

`illustration.inserer_dans_sorties: false` par défaut. Armée, les images retenues entrent dans
le Markdown assemblé, au début du premier chapitre qui **nomme le personnage** — le nom vient
du sidecar, pas d'une devinette —, avec une légende obligatoire sous chacune.

⚠ **La légende n'a pas d'interrupteur** : `core/insertion.py` lève sur une légende vide, il
n'y a aucune clé pour la vider, et son texte vient du **pack de langue cible** (nouvelle
consigne `legende_illustration_ia`, déclarée en français et en anglais). C'est la lecture de
l'art. 50 de l'AI Act retenue au lot 24, transposée à la sortie visible : le marquage machine
est dans le PNG, la mention lisible est sous l'image.

⚠ **C'est un paragraphe ordinaire en italiques, pas un style Word.** Ajouter un style
« Légende » romprait le contrat de styles de `langues/<code>/templates/reference.docx`, ce que
la règle de numérotation de ce fichier désigne comme un MAJEUR. Vérifié **format par format,
avec le vrai Pandoc** : DOCX, EPUB et PDF.

⚠ **Le light novel n'importe pas la brique d'illustration**, et ne doit pas : tout passe par
`core/insertion.py`. On peut effacer `illustration/` et rendre un tome.

### 6. Ce qui a été affaibli, et c'est écrit

`tests/test_imports_briques.py` tenait que **personne** n'importe `illustration/`. L'onglet
d'atelier crée forcément cette arête depuis `gui/`. Ce qui reste vrai, et qui est désormais
testé pour de bon : `pipeline/`, `manga/`, `scan/` et `core/` ne l'importent pas ; **aucun
import de niveau module** dans `gui/` ; et un test d'exécution rend `illustration`
inimportable puis **construit la fenêtre entière**, qui affiche alors un état vide expliquant
pourquoi l'onglet est vide.

### Vérifié

- `ruff check .` passe. `python -m pytest -q -m "not modeles and not lent"` passe.
- **Tests neufs : 129**, dont **17 seulement exigent Qt** — 86,8 % de la logique de ce lot se
  teste sans PySide6, ce qui est exactement ce que la règle de couche demandait. Comptés le
  2026-09-02 : **3 811 collectés avec PySide6, 3 592 sans**, soit **219 tests d'interface**,
  contre **3 682 / 3 480** (202) avant le lot. ⚠ Le `00-CONTEXTE-AGENT.md` annonçait
  2 007 / 1 879 : ce dénominateur datait du 2026-08-26 et il est faux depuis longtemps.
- Empreinte SHA-256 de `config.yaml`, et les treize critères numérotés du plan plus trois
  exigences non numérotées repris un par un — y compris les non tenus — dans
  **`docs/mesures/atelier-illustration-2026-09-02.md`**.

⚠ **Aucun cache n'est invalidé** : `manga/checkpoints.py:STAGES` et `FORMAT_VERSION` ne sont
pas touchés, `requete.yaml` garde sa version de schéma, et `bible.yaml` gagne un champ
`images_generees: []` que `fill_defaults` écrit sur les entrées existantes sans rien perdre.

## [2.20.0] - 2026-09-01

### MINEUR — Changer de police ne perd plus de répliques, et ne bascule plus en silence

Passer `manga.typeset.font_path` de Comic Neue à une autre police a produit un tome qui
« n'avait pas appliqué le changement » sur certaines planches. Les 150 pages avaient pourtant
bien été re-rendues : le cache n'y était pour rien. Deux défauts, tous deux **silencieux**,
tous deux réveillés par la police.

### 1. Le lettrage changeait de police bulle par bulle, sans une ligne de rapport

`typeset.font_pour_texte` choisit la police **par bulle** : si un seul caractère manque, TOUTE
la réplique est redessinée dans la première police de repli qui la couvre. Et un repli
« propre » — la chaîne a trouvé une police couvrante — n'alimentait **aucune** entrée de
rapport : `typeset_page` ne signalait que les caractères *substitués* ou *supprimés*.

Mesuré sur manga A / Vol.1, `font_path` sur Wildjess (135 glyphes) :

| police effective | bulles |
|---|---|
| celle demandée | 755 |
| `ComicNeue-Bold.ttf` | 60 |
| `l_10646.ttf` (Lucida Sans Unicode) | 3 |

**63 bulles sur 818, sur 45 planches sur 150.** Caractères en cause : `«` ×17, `œ` ×16,
`»` ×14, `Ç` ×11, `—` ×8, `À` ×5, `♪` ×2. Le seul indice existant était une ligne de
`RAPPORT.md` qui ressemblait à une note d'installation PSD.

- **`tools/completer_police.py`** complète une police à partir de ses PROPRES tracés :
  l'accent grave est détaché du `È` et reposé sur le `A`, la cédille du `ç` sur le `C`, le
  tiret cadratin est un trait d'union étiré, `œ` un `o` et un `e` accolés au recouvrement
  mesuré sur une police qui a un vrai `œ`. Ce que la police ne peut pas produire (`♪ ♥ ~ |`)
  est greffé depuis une autre, et **le résumé le dit glyphe par glyphe**. Les guillemets
  sont greffés par défaut : la synthèse par chevrons a été essayée, rendue et comparée à
  l'œil — elle donne `<<`, pas `«`. `--guillemets synthese` la garde disponible.
  ⚠ L'outil produit un **travail dérivé** ; `NOTICE` dit ce que cela engage.
- **Un pré-vol**, dans les premières secondes du run et avant tout chargement de modèle,
  mesure la police sur les traductions en cache : les signes absents, le nombre de bulles et
  de planches qui basculeront, et la largeur relative à `ComicNeue-Bold`. Il aura fallu dix
  minutes de rendu et une relecture de `RAPPORT.md` pour apprendre ce qu'il dit en deux
  secondes.
- **`--check` ne ment plus.** Il affichait « ✓ police trouvée », ce qui est toujours vrai :
  `resolve_font` retombe EN SILENCE sur la chaîne par défaut quand `font_path` désigne un
  fichier absent. Les polices non livrées avec le dépôt étant absentes de toute autre
  machine, un tome entier pouvait sortir en Comic Neue sans un mot.

### 2. Deux répliques avaient purement disparu de la planche

Le test de « région dégénérée » (`typeset.best_fit`) réunissait trois critères dans un même
`or`. Deux sont **géométriques** ; le troisième mesure un mot avec la police, et dépend donc
d'elle. La police retenue étant ~1,3× plus large à corps égal (`J'aimerais` à 8 px : 34
unités contre 45), ce seul critère a fait basculer page 22 bulle 2
(« J'aimerais bien tirer. ») et page 68 bulle 5 (« Katch ») du côté « dégénéré ». Or le
nettoyage avait **déjà effacé le japonais** : la planche est sortie avec deux bulles
blanches, et le message conseillait « corriger la détection » alors que la détection n'avait
pas bougé d'un pixel.

- **La géométrie fait toujours renoncer, la police jamais.** Un texte rogné se voit et se
  corrige ; une bulle blanche se lit comme un silence voulu. Nouveau motif d'échec
  `police_trop_large`, avec le conseil qui va avec — et qui n'accuse plus la détection.
- **Le critère de largeur se dédouble**, et l'oublier a d'abord mal classé la page 80 :
  « un mot ne tient pas » se corrige en changeant de police, « pas même une lettre ne
  tient » ne se corrige pas du tout. Cette bulle-là fait **4 px de large pour 258 de haut**,
  donc `dispo = 1 px` : son aire utile passe le seuil, sa hauteur aussi, et pourtant aucune
  police n'y écrira jamais. La mesure porte sur la plus étroite **lettre** du texte et non
  sur son caractère le plus étroit — le point de ComicNeue-Bold fait 1,0 px à 8 px, et
  « tenait » donc dans le couloir d'un pixel.
- **Nouveau motif `replique_non_dessinee`**, avec son avertissement console et sa section de
  rapport, placée en tête des incidents : c'est le seul où du texte disparaît. Il nomme la
  réplique perdue, et dit laquelle des deux issues s'est produite (bulle blanche, ou japonais
  conservé). Il a immédiatement révélé **six pertes**, toutes préexistantes et aucune
  signalée jusqu'ici : quatre régions dégénérées (pages 80, 134×2, 146) dont le rapport ne
  disait pas quel texte tombait, et **deux que rien du tout ne montrait** — pages 44 et 142,
  où le nettoyage a renoncé et où la traduction n'est allée nulle part.

### 3. Trois pièges silencieux, trouvés en passant

- **`typeset.POLICES_LIVREES` était relatif au répertoire courant** : lancé d'ailleurs que de
  la racine, le repli sautait aux polices système — un tome en Arial, sans un mot. Et
  `POLICES_SYMBOLES["win32"]` contenait `comic.ttf` et `arial.ttf` **sans dossier**, filtrés
  par `Path.exists()` : ils n'ont jamais été trouvés. Le commentaire promettait trois
  candidats Windows, il n'y en avait qu'un.
- **`mise_en_page.json` acceptait une clé `police`** que `typeset_page` n'applique jamais.
  Retirée des deux listes de champs reconnus : une clé ignorée vaut mieux qu'une clé qui
  promet.
- **La signature du cache d'aperçu de la GUI ignorait la police.** Éditer `config.yaml`
  pendant que la GUI est ouverte ne changeait aucune signature : les aperçus montraient un
  lettrage que le rendu ne produisait plus.

### Vérifié

Tome complet re-rendu, 150 planches, 818 bulles. Le pré-vol ne signale plus aucun glyphe
absent, et `RAPPORT.md` ne cite plus qu'**une** police (`WildjessComplet`) contre trois. Les
deux bulles blanches dues à la police (pages 22 et 68) sont lettrées et signalées
`police_trop_large`. Six répliques manquantes sont désormais listées nommément — elles
l'étaient déjà toutes avant ce lot, aucune n'est causée par lui.

**Non-régression, mesurée et non affirmée.** `best_fit` rejoué sur la géométrie réelle des
cinq bulles que le run du 2026-08-31 avait signalées, avec l'ancienne police : **5 décisions
sur 5 identiques**, causes comprises. Le nouveau code ne change rien à ce qui allait bien.

⚠ Les nouvelles sections de rapport ne se remplissent que pour les pages **re-rendues** depuis
ce lot : `--from rendu` pour une mesure complète du tome. Aucun cache n'est invalidé — les
`qa.json` d'avant ce lot restent lisibles et ne comptent rien plutôt que d'inventer.

## [2.19.1] - 2026-08-31

### CORRECTIF — Un refus juste, mais au mauvais moment

Aucun changement d'interface ni de sortie : ce lot **déplace un message** et en **corrige un
test**.

**Le piège, trouvé au premier usage réel hors session de développement.** Armer
`illustration.identite.actif` en laissant `illustration.comfyui.workflow` sur le graphe
**texte-vers-image** livré par défaut fait échouer la génération avec « canal références
refusé par le moteur ». Le refus est juste — « une requête dont un canal a été jeté sans un
mot produirait une image plausible et fausse » — mais il tombait **au moment de générer** :
après avoir choisi son personnage, relu cinq images une par une, relu cinq attributs, et tapé
son nom.

- **l'atelier le dit dans son bandeau**, avant la première question, et propose de continuer
  quand même — une description personnalisée sans référence passe très bien sur ce graphe ;
- **`--check` croise les deux clés** au lieu de les lister séparément. Il affichait déjà
  « identité : ARMÉE » puis « canaux honorés : prompt, prompt_negatif » — deux lignes justes,
  et personne ne fait le rapprochement. C'est le croisement qui informe ;
- **le message donne le chemin exact** du workflow à mettre, et ce que coûte l'autre issue
  (« désarme l'identité — le modèle inventera alors un visage »). « Configurez le canal »
  n'aide personne ;
- **`illustration.identite.actif` porte l'avertissement dans `config.yaml`**, là où on le lit.

### Un test du dépôt punissait qui arme la brique

`test_le_defaut_du_depot_est_bien_desarme` lisait `config.yaml` **sur le disque**. Armer la
brique — le geste normal pour s'en servir — faisait donc échouer la suite, sur un test qui ne
dit rien de l'installation et tout de ce que le projet publie.

Il lit désormais **`git show HEAD:config.yaml`**, qui est la définition de « livré ». Hors
dépôt git, il retombe sur le fichier et **saute** avec son motif si la copie locale est armée.
Un test qui échoue sur une configuration légitime apprend à ignorer les échecs.

### Vérifié

Sur le cas exact qui avait échoué, workflow d'édition armé : portrait produit en **857,7 s**,
une référence retenue sur cinq, cinq attributs sur cinq validés — et l'image les porte tous.

Tout est dans `docs/mesures/atelier-2026-08-31.md` §3.4.

## [2.19.0] - 2026-08-31

### MINEUR — Une seule commande, une œuvre entière, et trois défauts que seul l'usage pouvait montrer

> **Rien n'est périmé pour qui n'a rien armé.** `illustration.actif` vaut toujours `false` :
> `run.py`, `run_manga.py` et `run_ocr.py` sont iso-comportement.
>
> ⚠ **MIGRATION, pour qui avait ARMÉ la brique.** La sortie passe de
> `build/<Projet>/<Tome>/illustrations/` à **`build/<Projet>/illustrations/`**. Un
> `requete.yaml` resté sous un tome n'est **ni lu ni déplacé** : la phase 1 le **nomme** à
> l'écran, et c'est à toi de recopier ce que tu veux garder. Déplacer le travail de relecture
> de quelqu'un sans le lui dire serait pire que de l'ignorer.
>
> Ce n'est pas classé MAJEUR parce qu'aucun cache n'est invalidé, qu'aucune commande ne change
> de forme, et que la brique est expérimentale et désarmée par défaut — mais la ligne est
> mince, et c'est pourquoi elle est écrite ici plutôt que dans une note de bas de page.
>
> Empreinte SHA-256 de `config.yaml` après le lot :
> `cd7232f1e9a61d62fc79cb97f4cc602e66d11393c091000bf502cbd76b4ba8a6`.

**Une commande suffit :**

```powershell
python run_illustration.py "Mon LN"
```

Elle demande **qui illustrer** — parmi les personnages de l'œuvre, les mieux documentés
d'abord —, ou laisse **écrire soi-même** la description qu'on veut. Puis le cadrage, le nombre
d'images, **quelles images montrer au modèle** (une par une, avec ce qu'on en sait et, si on
le demande, ce que le modèle de vision en dit), et enfin la validation : le prompt complet
s'affiche avec **d'où vient chaque mot**, et répondre demande **un nom**.

**Une ŒUVRE, pas un tome.** Les références d'un personnage vivent où l'éditeur les a mises :
la brique lit désormais tous les volumes — `media/` et `chapters/` — et écrit dans un dossier
unique. Le lot a tourné sur une œuvre de **4 tomes, 98 images dont 80 exploitables, 35
personnages et 25 chapitres traduits** : cinq fois le corpus qui avait servi jusque-là.

### Les défauts du lot 26, corrigés

- **le cache d'exécution de ComfyUI** resservait le résultat d'un run INTERROMPU — une image
  partiellement débruitée, marquée et écrite comme les autres. Le moteur **refuse** désormais
  une génération rendue en moins de `illustration.comfyui.plancher_secondes` (**2,0 s**), et
  le refus tombe **avant le téléchargement** : aucune image issue du cache n'existe jamais sur
  le disque. Le plancher vient d'un chiffre — la génération la plus rapide relevée sur cette
  pile est de 16 s par pas de débruitage ;
- **le classifieur ne voyait que la couverture en `p1`.** Une couverture republiée ailleurs
  dans le volume — le cas courant d'un EPUB — était rangée en `pleine_page`, et le mécanisme
  du lot 25 qui repousse les couvertures ne se déclenchait donc pas sur celles qui en avaient
  le plus besoin. Détection de **sosie** ajoutée, seuil **0,70** posé dans un vide mesuré
  (republications 0,797 à 1,000 ; tout le reste 0,314 à 0,594, sur six tomes de deux œuvres).
  Sur le corpus de comparaison, les couvertures détectées passent de 1 à **2 par tome** ;
- **la ponctuation du prompt, le comptage des appels de la phase 1 et l'étiquette de modèle**
  étaient déjà corrigés au lot 26 ; leurs garde-fous sont maintenant **testés** —
  `tests/test_illustration_correctifs.py` fait échouer la suite si l'un des défauts revient.

### Les trois défauts que seul l'usage a montrés

- **une référence sans son tome est AMBIGUË.** `roman N` a un `image1` dans son Vol.1 **et**
  dans son Vol.2 ; la résolution rendait le premier venu, en silence, et le modèle d'image
  pouvait donc recevoir le personnage d'un autre volume. La passe de propositions écrit
  désormais `<Tome>/media/<nom>`, et `requete.verifier` **signale** l'ambiguïté des bibles
  déjà écrites au lieu de la trancher au hasard ;
- **une classification ne doit pas dépendre d'un drapeau de vitesse.** La détection de sosie a
  d'abord été adossée à `avec_couleurs` — et le correctif ne remontait alors pas jusqu'au
  sélecteur de références, c'est-à-dire jusqu'au seul endroit pour lequel il avait été écrit.
  Coût publié à la place : le classement à sec d'une œuvre de 98 images passe de **0,03 s à
  1,09 s** ;
- **une revue en bloc ne vaut rien.** Sur le premier personnage réellement relu, la passe
  automatique proposait cinq attributs dont **trois faux** — dont des cheveux « bleu céleste »
  là où le dessin les montre verts, la phrase citée décrivant **un autre personnage**. Un
  « o/n » global n'aurait laissé que deux issues : écrire trois erreurs, ou perdre les deux
  bons attributs. La revue se fait donc **attribut par attribut, citations sous les yeux**.

### Ajouté

- **`illustration/atelier.py`** — ce qu'il faut savoir pour poser les questions : qui est
  illustrable et dans quel état (`prêt`, `à relire`, non proposé **avec son motif**), quelles
  images sont candidates, comment filtrer une entrée proposée, et comment inscrire une revue
  dans la bible. **En Python nu**, sans `rich` et sans `input()` : la règle de couche du dépôt.
- **`illustration/console.py`** — les questions, et rien d'autre. La façade console.
- **`core/illustrations.py:inventaire_projet`, `relatif_au_projet`, `sosies_de_la_couverture`,
  `empreinte_perceptuelle`** — l'œuvre entière, la référence qui porte son tome, et la
  détection de couverture republiée.
- **`core/bible.py:chemins_de_reference`** — rend **tous** les chemins auxquels une référence
  répond. Rendre la liste plutôt qu'un booléen est ce qui permet de voir l'ambiguïté.
- **`illustration.comfyui.plancher_secondes`** — 2,0 s, 0 pour désarmer.
- **`docs/procedures/illustration.md`** — la fiche de la brique : quoi lancer, dans quel
  ordre, quelles clés changent le résultat, et « quand ça ne marche pas ».

### Modifié

- **`illustration/scene.py:passages`** lit les chapitres de **toute l'œuvre**, et la source
  citée porte le tome (`Vol.2/chapters/ch03.md`) quand la racine en couvre plusieurs.
- **`requete.verifier`** perd son paramètre `dossier_tome` : il désignait une racine trop
  étroite, et en garder deux invitait à les confondre.
- **`tools/bible.py --proposer`** écrit les références préfixées par leur tome.
- **L'atelier lit aussi `bible.propositions.yaml`.** Sans cela, une œuvre neuve — qui n'a pas
  encore de `bible.yaml` — n'aurait rien à proposer : sur `roman N`, **11 personnages
  illustrables sur 23 proposés**, tous à relire.

### Le résultat qui tient en une image

Run complet sur `roman N` : 9 images candidates, **2 retenues**, **3 attributs sur 5 rejetés**
à la revue. Le prompt final ne portait plus que « yeux verts, porte manteau sobre » — et
**l'image produite a les bons cheveux**, verts comme les illustrations, alors que le mot ne
figure nulle part dans le prompt. C'est la démonstration la plus nette de ce que le lot 26
avait mesuré : **ce sont les références qui portent l'identité, pas les mots.**

### Non fait, et dit

- **La revue de `roman N` n'est pas celle de l'auteur du projet.** Un seul personnage sur 23
  a été relu, par l'agent qui a écrit ce lot, en ouvrant les neuf images et en lisant chaque
  citation — et le sidecar de l'image produite le dit mot pour mot. Les 22 autres attendent
  une revue qui n'appartient pas à cet agent.
- **Le plancher anti-cache n'a pas été vérifié contre un vrai cache** : le reproduire
  demanderait d'interrompre volontairement une génération, ce qui coûte 22 minutes de
  rechargement de modèle. Il est testé contre un doublon qui répond instantanément — même
  symptôme, pas même cause.
- **56 abstentions sur 80** à la passe vision de `roman N` : comptées, pas vérifiées image
  par image.
- **La ressemblance n'est toujours pas mesurable** (juge du lot 25 à 68/100), et le protocole
  humain en aveugle n'a toujours pas été exécuté.

Tout est dans `docs/mesures/atelier-2026-08-31.md`.

## [2.18.0] - 2026-08-30

### MINEUR — Le prompt vient de l'œuvre. Et ce n'est pas sa FORME qui décide, c'est le CHOIX des images

> **Rien n'est périmé, rien n'est à supprimer.** `illustration.actif` vaut toujours `false`,
> `illustration.moteur` toujours `"factice"`, `illustration.identite.actif` toujours `false`,
> et les clés neuves `illustration.prompt.llm.actif` et `illustration.prompt.ancrages_max`
> valent `false` et `0` : `run.py`, `run_manga.py` et `run_ocr.py` sont iso-comportement.
>
> ⚠ **Une seule chose change pour qui avait ARMÉ la brique** : la forme du prompt. Un
> `requete.yaml` du lot 25 disait « Portrait d'un personnage seul, en pied, sur fond neutre. …
> » ; il dit maintenant « un personnage seul, en buste, cadré à mi-corps, sur fond neutre. …
> » suivi, quand le tome a une signature mesurée, de son registre en mots. Le schéma de
> `requete.yaml` passe de 1 à 2, et **un fichier de version 1 se relit sans perdre sa
> validation**.
>
> Empreinte SHA-256 de `config.yaml` après le lot :
> `25fd55b59379f1114b5cf64c3e1f1540c413897a5ae28d2e40c9168f6274ac25`.

**Le `PLAN-26` demandait de mesurer la forme du champ texte. Le premier run réel a répondu à
une autre question, et c'est elle qui commande ce lot.**

Le lot 25 avait écrit, chiffres à l'appui : « les générations sont **en couleur**, le tome est
**en noir et blanc**, et cinq images de plus n'y changeront rien. » Il avait raison sur le
mécanisme — « le conditionnement rapproche l'image du registre des RÉFÉRENCES, pas du registre
du TOME » — et tort sur la conclusion. **Ce n'est pas le nombre d'images qui compte, c'est
lesquelles.**

Le modèle de vision du dépôt (`yume-27b`) lit ce que le classifieur déterministe du lot 23 ne
voit pas. Sur les 10 références validées du corpus, il désigne « couverture avec titre, nom
d'auteur, numéro de tome » sur des fichiers que `core/illustrations.py` range en `pleine_page`
— dont la **page *Afterword***, qui porte le mot de l'illustrateur et sa signature. **Quatre
motifs vérifiés à l'œil sur quatre sont exacts.**

Conséquence mesurée, une seule variable changée — le choix des images, même graine, même
prompt, même workflow :

| sélection | même régime de couleur que le tome ? |
|---|---|
| déterministe (couverture + page à texte) | **non ✗** |
| modèle de vision (portrait au trait) | **oui ✅** |

⚠ **Et l'écart moyen aux quatre descripteurs ne bouge pas** — 0,12 contre 0,13. Une moyenne
identique pendant qu'un descripteur binaire bascule est exactement ce que le critère 4 ter du
`PLAN-25` interdit de moyenner.

**Un SECOND levier, indépendant du premier, fait basculer le même descripteur.** `bible.style.
mots` est vide sur ce corpus ; le lot ajoute `mots_de_signature`, qui traduit la signature
mesurée par le lot 23 en mots dicibles à un modèle d'image — « en noir et blanc, palette
désaturée, trait marqué, larges aplats uniformes ». Résultat, à références **inchangées** :

| approche de style | jetons | écart moyen | même régime de couleur |
|---|---:|---:|---|
| 3 — ne rien faire | 79 | 0,12 | **non ✗** |
| **1 — les mots de la signature** | **104** | **0,11** | **oui ✅** |
| 2 — une ancre sur le canal d'images | 107 | **0,10** | non ✗ |

L'approche 1 est retenue : elle est la seule qui corrige le régime, pour **+25 jetons** et
aucune image de plus. L'approche 2 donne le meilleur écart moyen, ne corrige pas le régime,
coûte une place du canal — le graphe en expose trois, dont deux sont prises par l'identité — et
2,7 fois plus de temps : elle est **livrée désarmée**, avec le tableau qui le décide.

⚠ **Le choix par le modèle est livré DÉSARMÉ**, et c'est une mesure qui le décide : armé, il
fait passer le corpus de **4 personnages illustrables à 1**. Ses refus sont justes sur les
faits — une page *Afterword*, un visage masqué, une composition à deux — et ils mesurent la
qualité du corpus plutôt qu'ils ne la dégradent. Mais ce n'est pas un verdict à imposer par
défaut à quelqu'un qui n'a rien demandé.

### Ajouté

- **`illustration/prompt.py`** — la charpente **déterministe** du prompt. Pure : aucun réseau,
  aucun modèle, aucun fichier hors du gabarit ; deux appels de mêmes arguments rendent deux
  requêtes de même empreinte, ce qui est la condition pour que tous les balayages de ce lot
  soient comparables. Les fragments d'apparence viennent de `bible.apparence` filtrés par
  `bible.citations[]`, **et de nulle part ailleurs** — ce n'est pas une vérification, c'est
  une absence de branche. Porte aussi `mots_de_signature`, qui traduit la signature mesurée du
  lot 23 en mots dicibles à un modèle d'image.
- **`illustration/selection.py`** — quelles images montrer, et **pourquoi**. Un motif d'une
  ligne par image, **retenue comme écartée** : sans lui, la porte humaine se réduit à un clic
  de confiance. Plafond de **2 références**, qui est le verdict mesuré du lot 25 (« la rupture
  est entre 1 et 2, pas entre 2 et 3 ») et non la limite câblée du graphe (3). Une image
  **générée** n'est jamais candidate, et c'est un test, pas une intention.
- **`illustration/scene.py`** — l'appel LLM facultatif de L26.2 : le modèle reformule un
  passage du chapitre en une phrase de **pose**, jamais en attribut. Le plafond de jetons
  écarte des passages **entiers** ; il n'en tronque aucun. Le run de bout en bout en a produit
  deux, bonnes — « Sorti de la tranchée, il tient son miroir de reconnaissance, le visage las,
  sous la pluie » — et **aucune image ne les porte** : les deux personnages concernés n'ont pas
  de référence validée, et la phase 2 refuse de produire sans référence. L'apport de la clause
  reste donc **non mesuré**.
- **`illustration/gabarits/`** — la **syntaxe d'un modèle d'image**, versionnée, avec son
  empreinte SHA-256 dans le sidecar de chaque image. Distincte de `langues/<code>/prompts/`,
  qui porte la voix d'un tome : mélanger les deux ferait dépendre la reproduction d'une
  traduction de la version d'un générateur d'images.
- **Quatre fichiers de prompt**, nommés comme la règle MINEUR du présent fichier l'exige, avec
  leur en-tête de licence **en fin de fichier** (interdit n° 6) et **hors**
  `core.langues.PROMPTS_REQUIS` — le modèle est `manga_relecteur.md`, livré dans les deux packs
  et absent du tuple :
  - `langues/fr/prompts/illustration_portrait.md` et `langues/en/prompts/illustration_portrait.md`
    — le **cadreur** : il décrit ce que le personnage FAIT, jamais à quoi il ressemble ;
  - `langues/fr/prompts/illustration_style.md` et `langues/en/prompts/illustration_style.md`
    — le **documentaliste iconographique** : il juge une image pour un usage précis, en trois
    lignes.
- **`tools/banc_prompt.py`** — le banc du lot : `--fragments` (aucun réseau), `--canaux`
  (relevé sur le serveur réel, pas lu dans une page web), `--selection [--llm]`, et quatre
  balayages qui génèrent (`--references`, `--style`, `--formes`, `--langues`).
- **`illustration.prompt.*` et `illustration.budget.*`** — forme du champ texte, langue du
  prompt d'image, cadrage, gabarit, approche de style, plafonds. Tous à un défaut
  iso-comportement.

### Modifié

- **`requete.yaml` passe au schéma 2.** `references` devient une liste d'objets
  `{fichier, motif, retenue}` ; `ancrages_style` apparaît à côté — deux usages du **même**
  canal d'images, distingués jusque dans le texte du prompt ; `entites` et `image_controle`
  se rangent sous `canaux`, parce que ce ne sont pas du texte mais des **arguments typés** ;
  `attributs_sources` dit d'où vient chaque mot ; `graine: null` veut dire aléatoire.
  **Un fichier de version 1 se relit, et il reste validé.**
- **La phase 2 HONORE le fichier relu, elle ne redérive plus rien.** C'était le défaut du
  lot 25 : `requete.yaml` portait des références et la phase 2 les recalculait depuis la
  bible, donc un utilisateur qui en décochait une la voyait revenir. Une porte humaine dont
  les décisions sont recalculées derrière n'est pas une porte.
- **Le sidecar de provenance porte `prompt_source`** : gabarit, **son empreinte**, forme,
  langue, cadrage et la source de chaque attribut. Le payload rejoue le MOTEUR ; ce bloc
  rejoue la PHASE 1.
- **`RAPPORT.md` de la brique** gagne « d'où vient ce visage » — attribut, valeur, fichier
  cité, origine — et le tableau des images montrées au modèle **et de celles qui ne l'ont pas
  été**. Il met aussi le temps de la phase 1 face à celui de la phase 2.
- **Le genre du prompt vient du GLOSSAIRE quand la bible se tait.** `bible.genre_confirme` est
  vide sur **11 personnages sur 11** du corpus ; le glossaire du même projet le porte pour
  **9 sur 11**. Un champ que la bible ne remplit jamais et qu'un autre fichier du même dépôt
  porte déjà n'est pas une donnée manquante. Les deux sources sont distinctes — l'une confirmée
  sur un dessin, l'autre sur le texte — et **le sidecar dit laquelle a parlé**.

### La chaîne complète a tourné, et le rejeu est exact

Bout en bout sur le corpus réel, modèle de vision armé : phase 1 en **298,4 s** (13 appels de
vision, 6 de texte), porte humaine, phase 2, puis rejeu depuis le sidecar seul —
**octet pour octet identique à l'original**. Le lot 24 avait laissé la question ouverte en
écrivant « la plupart des backends de diffusion ne sont pas déterministes » ; sur cette pile,
ils le sont.

Mieux qu'un rejeu isolé : **la même requête a été exécutée quatre fois** dans la session, par
quatre commandes différentes et à des états de VRAM différents (facteur 2,7 sur le temps), et
les trois grandeurs mesurées sont **identiques à la deuxième décimale** sur les quatre.

Le run a aussi exercé le reste : le **plafond de budget** a mordu (11 candidats → 8, motif
nommé au journal et dans `RAPPORT.md`), **7 personnages sur 8 ont été refusés** faute de
référence validée retenue, et le `RAPPORT.md` porte « d'où vient ce visage » — attribut, valeur,
fichier cité, origine — ainsi que le tableau des images montrées au modèle **et de celles qui
ne l'ont pas été**.

### Le second battant de la porte humaine

`valide: false` refusait déjà. **Décocher toutes les références d'un personnage qui en avait**
refuse maintenant aussi, **avant la bascule VRAM** et avant le chargement de 12 Go de poids.
Il ne se confond pas avec le refus du lot 25 : « l'humain a tout décoché » et « la bible ne
documente pas ce personnage » se ressemblent dans le fichier et pas du tout dans la vie — et
sur ce corpus, 7 personnages sur 11 sont dans le second cas.

### Non fait, et dit

- **Aucun canal structuré n'est livré.** Les licences d'`EliGen-V2` et du ControlNet blockwise
  ont été **vérifiées à la source primaire** (Apache-2.0 toutes les deux) et les nœuds
  inventoriés sur le serveur réel — mais **le coût VRAM n'a pas pu être mesuré** : aucun de
  ces poids n'est installé, `ModelPatchLoader` expose une liste vide, et les télécharger pour
  mesurer un canal dont l'apport n'est pas mesuré est l'ordre exact que le plan interdit. La
  **marge** est publiée à la place : 8,4 à 9,1 Go libres après une génération réelle.
- **Les dénominateurs sont petits.** Le plan demande 10 images par axe ; les axes qui génèrent
  ont tourné sur **un personnage** — le seul du corpus à porter plus d'une référence validée —
  et 2 à 3 images par axe.
- **La ressemblance n'est toujours pas mesurable** : le juge du lot 25 ne sépare que 68 fois
  sur 100, ses verdicts restent marqués « non opposables », et le protocole humain en aveugle
  du `PLAN-25` étape 0.3 **n'a toujours pas été exécuté**.
- **L'apport de la clause de scène n'est pas mesuré.** `illustration/scene.py` est complet et
  testé ; aucune image de ce lot n'en porte.
- **Le défaut du classifieur de couvertures n'est pas corrigé, il est contourné.**
  `core/illustrations.py` manque au moins trois pages typographiées de ce corpus ; un
  utilisateur qui n'arme pas le modèle de vision garde le défaut entier.
- **`bible.references[].cadre` est toujours vide sur les 10 références.** L'axe « nature du
  recadrage » de `PLAN-25` L25.1 reste non mesuré, pour la deuxième fois.

Tout est dans `docs/mesures/prompt-illustration-2026-08-30.md`, y compris **trois défauts
trouvés en mesurant** et publiés plutôt que corrigés en silence :

- la variante « mots » du balayage de style produisait un prompt **identique** à la variante
  « aucun » — `bible.style.mots` étant vide — et ComfyUI avait rendu la seconde image en
  **1 seconde** depuis son cache d'exécution. C'est ce défaut qui a fait écrire
  `mots_de_signature` ;
- après un `POST /interrupt`, le **même cache a rendu le résultat du run INTERROMPU** : une
  image partiellement débruitée, servie en 1,1 s, que seule sa mesure de style (0,23 au lieu de
  0,12) a trahie. Et cet `/interrupt` a coûté au run suivant une réinitialisation de modèle de
  **22 minutes**. Le principe retenu est de laisser la file se vider plutôt que d'interrompre ;
- `phase1.appels_llm` ne comptait que les appels de **vision**, pas ceux des clauses de scène :
  le run publié affiche « 13 appels » pour une phase 1 qui en a fait **19**. Le correctif est
  livré, le chiffre du tableau reste celui du run, et la correction est écrite à côté.

Un quatrième défaut, celui-là dans le prompt lui-même, a été trouvé en relisant une requête
réelle : la clause de style n'était pas close par un point, et « larges aplats uniformes Le
personnage est celui de l'image 1 » soudait deux phrases dans un champ que lit un modèle de
langue. Corrigé avant livraison ; les six prompts déjà mesurés ont été vérifiés byte-à-byte
**identiques** après le correctif, seul le balayage de style était concerné et il a été relancé.

## [2.17.0] - 2026-08-29

### MINEUR — L'identité : la voie A produit enfin le bon registre, et le juge qui devait l'arbitrer ne sépare pas

> **Rien n'est périmé, rien n'est à supprimer.** `illustration.actif` vaut toujours `false`,
> `illustration.moteur` toujours `"factice"`, et la clé neuve `illustration.identite.actif`
> vaut `false` : `run.py`, `run_manga.py` et même `run_illustration.py` sont iso-comportement.
> Ce lot ajoute une capacité opt-in et **livre son garde-fou désarmé**, parce que la mesure ne
> soutient pas de l'armer.
>
> Empreinte SHA-256 de `config.yaml` après le lot : voir
> `docs/mesures/identite-2026-08-29.md`.

**Le `PLAN-25` est le seul de sa série qui a le droit de conclure « on ne le fait pas ». Il
conclut autrement, et sur deux plans opposés :**

- **la voie A marche, et sur le point où le lot 24 avait échoué.** Conditionner
  `Qwen-Image-Edit-2511` par les références validées de la bible produit des images **au trait
  et en noir et blanc**, là où le texte-vers-image du lot 24 rendait des photos en couleur avec
  cinq fois moins de trait. C'est mesuré avec l'outil du lot 23
  (`core/illustrations.py:signature`), pas jugé à l'œil ;
- **le juge automatique, lui, ne sépare pas l'identité.** Étalonné sur le corpus réel :
  présenté une paire « même personnage » et une paire « personnages différents de la même
  œuvre », il les classe dans le bon ordre **68 fois sur 100** — pour un seuil fixé à 80. Le
  même juge sépare **91 fois sur 100** une œuvre d'une autre. Il voit le tome, il ne voit pas
  la personne.

**Conséquence livrée : le garde-fou existe, il est complet, et ses verdicts d'identité sont
marqués « non opposables ».** `illustration.identite.planchers.juge_utilisable` vaut `false` par
défaut, et le sidecar de chaque image porte le score **et le plancher** auquel il a été comparé.

### Ajouté

- **`illustration/juge.py`** — l'encodeur d'image ONNX, le cosinus en numpy, et les **trois
  grandeurs** que le plan interdit de confondre : `ressemblance` (moyenne des cosinus aux
  références), `nouveaute` (1 − le cosinus à la référence la **plus proche**), `style` sur deux
  échelles (embedding **et** descripteurs déterministes, avec le descripteur qui décroche
  **nommé**). Pas d'OpenCV, pas de `torch`.
- **`illustration/identite.py`** — la voie A : références de la bible → recadrage →
  redimension → canal `references` du moteur, et les **quatre motifs de refus** de L25.2,
  nommés et comptés.
- **`illustration/workflows/qwen-image-edit-2511.api.json`** — le premier graphe du dépôt qui
  porte `%reference_1%`, `%reference_2%` et `%reference_3%`. Trois, parce que c'est ce que le
  nœud `TextEncodeQwenImageEditPlus` de ComfyUI 0.34.2 expose.
- **`tools/banc_identite.py`** — `--etalonnage` (les cinq planchers, aucun GPU),
  `--juge-variantes` (huit prétraitements en concurrence), `--balayage` (L25.1),
  `--triplets N` (le matériel du juge humain, **sans étiquette**).
- **`core/illustrations.py:descripteurs`** — les descripteurs d'**une** image, avec exactement
  les règles qui ont produit la signature du tome. Une seconde implémentation aurait rendu les
  deux nombres incomparables.
- **`frontiere.ecriture_extrait`** — la seule autre porte d'écriture d'image du dépôt, pour un
  **extrait de l'œuvre** et non une image générée. Elle est plus étroite que
  `ecriture_marquee` : un seul chemin à la fois, et seulement dans `references/`. Le marquage
  AI Act reste sans interrupteur.
- **le client ComfyUI téléverse ses références et élague les nœuds inutilisés** — mesuré :
  `LoadImage` **refuse** un chemin absolu (« Invalid image file »), donc il faut lui donner
  l'image par `POST /upload/image`. L'élagage est ce qui permet de balayer 1, 2 ou 3 références
  avec **un seul** workflow.
- **17 clés `illustration.identite.*`** dans `config.yaml`, toutes sans effet à `actif: false`.

### Le défaut que seul l'usage réel du canal de référence pouvait montrer

**Les trois premières références d'identité validées du corpus réel sont trois COUVERTURES de
light novel** — titre de l'œuvre, nom de l'auteur, nom de l'illustrateur et numéro de tome en
grandes lettres —, et **deux d'entre elles sont le même dessin** (cosinus 0,9637). Le lot 23
les avait validées à la main ; rien ne s'en plaignait tant que personne ne s'en servait.

Trois conséquences, toutes livrées :

- `retenir` **repousse les couvertures en dernier**. Ce n'est pas un tri par « meilleure »
  référence — le banc ne saurait pas le faire — c'est un fait que le dépôt connaît déjà :
  `core/illustrations.py` **classe** les couvertures et dit d'elles qu'elles portent « un logo
  d'éditeur et un bandeau de prix ». Elles restent utilisables quand elles sont la seule
  référence ;
- **une garantie du dépôt a une faille, et elle est nommée** : `marquage._sans_titre` refuse
  d'écrire le titre de l'œuvre dans les métadonnées d'un PNG, mais il inspecte du **texte**.
  Il ne voit pas un titre **peint** dans une image de couverture, et ces pixels partent au
  modèle. Aucune détection de texte n'est appliquée aux références — `illustration/` n'importe
  que `core/`, c'est une contrainte testée — et le lot le **dit** plutôt que de laisser croire
  le garde universel ;
- le run **le signale à l'utilisateur** pendant qu'il tourne, pas seulement dans un document.

### Un manifeste qui se trompait de modèle

`requete.yaml` porte un champ `modele` écrit par la phase 1 d'après la configuration
**d'alors**, et la phase 2 le recopiait dans le sidecar sans le confronter à rien. Un
`requete.yaml` validé la veille annonçait `qwen-image-2512-Q4_1` pendant que le graphe
d'édition chargeait `qwen-image-edit-2511-Q4_1`. Le client relève désormais **les fichiers de
modèle que le graphe nomme**, le manifeste porte les deux, et le PNG porte celui qui a
réellement produit l'image. Un manifeste qui se trompe de modèle est pire qu'un manifeste sans
modèle : il a l'air vérifiable.

### Mesuré, et publié dans `docs/mesures/identite-2026-08-29.md`

- **le corpus ne satisfait PAS l'étape 0.1 du plan**, et c'est écrit avant le premier chiffre :
  il demande 8 personnages dont ≥ 2 à trois références ou plus ; la bible réelle en porte
  **4 avec au moins une référence validée**, dont **un seul** à trois ou plus ;
- **les cinq planchers**, avec leur nombre de paires : identité haute 0,4649 (n = 21),
  confusion 0,3676 (n = 23), négatif 0,2530 (n = 400), style haut 0,4044 (n = 120), style bas
  0,2299 (n = 400) ;
- **huit prétraitements du juge mis en concurrence** ; le défaut retenu (`plein`, 224,
  `cls_moy`) va **contre** la recette amont, et la mesure dit pourquoi ;
- **une illustration de groupe sert de référence à deux personnages** — le cas que le
  critère 8 du plan demande d'examiner. Sa paire vaut 1,0 par construction et est **exclue** de
  la population de confusion ;
- **`ressemblance` et `nouveauté` dégénèrent en une seule mesure** sur un personnage à une
  seule référence — c'est-à-dire sur 3 des 4 personnages référencés du corpus.

### Non fait, et dit

- **l'étape 0.3 — le protocole en aveugle sur 20 comparaisons — n'a PAS été exécutée** : c'est
  un geste humain, et aucun code ne le remplace. Le banc en prépare le matériel
  (`--triplets`), le seuil (14 sur 20) est celui du plan, et il est fixé avant.
- **l'axe « nature du recadrage » de L25.1 n'a pas été mesuré** : la bible réelle porte des
  **pages entières** sans boîte de recadrage. Le champ `cadre` est livré et testé ; il est vide
  sur les 10 références du corpus, et balayer un axe à une seule valeur ne mesure rien.
- **la voie B (LoRA par personnage) n'a pas été ouverte**, et n'avait pas à l'être : le plan
  la subordonne à l'échec de A.

## [2.16.0] - 2026-08-29

### MINEUR — Le connecteur Qwen-Image, mesuré sur la 7900XT : six défauts que seul le réel pouvait montrer

> **Rien n'est périmé, rien n'est à supprimer.** `illustration.actif` vaut toujours `false` et
> `illustration.moteur` toujours `"factice"` : `run.py` et `run_manga.py` sont inchangés. Ce
> lot **arme** ce que la 2.15.0 avait livré désarmé faute de machine de mesure.
>
> Empreinte SHA-256 de `config.yaml` après le lot :
> `3e93c206a3504f00228d5e7bca77db29bb2edf937ad2d33851765b2d516fc762`.

**La 2.15.0 disait « le moteur réel n'a jamais tourné ». Il a tourné.** RX 7900 XT, ROCm 7.14,
ComfyUI 0.34.2, `Qwen-Image-2512` GGUF Q4_1 : **11 images sur 11** produites de bout en bout
sur le corpus réel `roman S` Vol.1, marquées et accompagnées de leur sidecar — et **0 échec sur
les 25 générations** de la journée, bancs compris.

**Les trois mesures que le `PLAN-24` n'avait pas pu faire sont faites**, et deux de ses
prémisses tombent :

- **étape 0.3 — le chemin ComfyUI est mesuré** : **103,7 s par image** à 4 pas et **629,8 s**
  à 50 pas (médianes sur 4 images chacune, 1328 × 1328), pic VRAM **14 421 Mio sur 20 464**,
  **0 échec sur 25 générations**. `stable-diffusion.cpp` et `diffusers` restent non mesurés, et
  le document le dit ;
- **étape 0.4 — les licences sont revérifiées à la source primaire** : `Qwen/Qwen-Image-2512`,
  `Comfy-Org/Qwen-Image_ComfyUI`, `unsloth/Qwen-Image-2512-GGUF` et
  `lightx2v/Qwen-Image-2512-Lightning` sont toutes **Apache-2.0** ;
- **la prémisse « ~10 Go en 4 bits » est corrigée par pesée** : le fichier réel fait
  **12 843 678 240 octets (12,84 Go)**, et son SHA-256 `a4cc7256…` est identique au nom du
  blob Hugging Face, donc vérifié contre l'amont.

**Deux workflows sont livrés, et seulement parce qu'ils ont tourné.** Le `PLAN-24` refusait
d'en livrer un — « en écrire un sans l'avoir exécuté aurait produit un fichier plausible et
faux » — et c'était juste. `illustration/workflows/qwen-image-2512.api.json` (50 pas, cfg 4) et
`…-lightning.api.json` (4 pas, cfg 1, LoRA Lightning) ont produit les images ci-dessus.

**Le réglage le plus contre-intuitif du lot est mesuré, pas deviné.** `CLIPLoader.device: "cpu"`
n'est pas un repli pour petite carte : l'encodeur de texte pèse 7 910 Mio et le transformeur
12 284 Mio, soit **20 194 Mio pour 20 464 Mio de VRAM**. Les garder tous deux sur la carte fait
basculer ComfyUI en mode « lowvram » (707 patches) et le pas passe de **6,7 s à 64,3 s** —
**facteur 9,6**. Encoder sur CPU rend la carte entière au transformeur.

#### Six défauts trouvés par l'usage réel, tous corrigés et couverts par un test

1. **`illustration/poids.py` bouclait jusqu'à l'abandon sur un téléchargement réussi.**
   `octets_attendus` n'était jamais corrigé par `Content-Length` (`total = total or …`) : une
   estimation surestimée de 166 octets sur le VAE faisait croire le fichier incomplet, puis
   demander un `Range` au-delà de la fin — **HTTP 416 en boucle**. `Content-Length` fait
   désormais foi, et **416 est lu pour ce qu'il est : « tu as déjà tout le fichier »**.
2. **`illustration/comfyui.py` jetait le corps des réponses d'erreur.** Un refus de ComfyUI
   arrivait en « HTTP Error 500 » et rien d'autre, alors que le corps porte le `node_errors`
   qui nomme le nœud fautif. Le corps est maintenant relayé.
3. **Une clé de commentaire à la racine d'un workflow faisait tomber ComfyUI en 500.** Il itère
   sur **toutes** les clés racine et appelle `.get('_meta')` sur chacune. Le dépôt vit de
   fichiers commentés : le client retire donc les clés qui ne sont pas des nœuds juste avant
   l'envoi, plutôt que d'interdire le commentaire.
4. **Deux règles de résolution des références coexistaient dans le dépôt.**
   `core/bible.py` accepte une référence sous **n'importe quel** tome du projet — la bible est
   par projet — quand `illustration/requete.py` ne cherchait que sous le tome courant. Sur
   `roman S`, **7 des 10 références vivent dans le Vol.2** et étaient déclarées introuvables.
   `core.bible.reference_existe` est publique et devient **la** règle ; il n'y en a plus deux.
5. **Le prompt ignorait `genre_confirme`.** Vu à l'œil sur le premier run : « Gale », décrit
   « adulte, cheveux courts foncés, uniforme militaire », est sorti **en femme**. Le champ
   central de la bible — `core/glossary.py` étiquette lui-même la catégorie « Personnages (le
   genre commande les accords) » — n'entrait pas dans le prompt. Il y entre, **accordé**, et
   seulement quand il est confirmé : l'abstention reste le défaut.

6. **Un commentaire pouvait déclarer un canal que le workflow n'honore pas — le plus grave des
   six.** `CANAUX_SUPPORTES` se lisait dans le **texte brut** du fichier ; le commentaire du
   graphe de référence, qui écrit qu'il ne porte « NI `%reference_1%` NI `%masque_1%` NI
   `%image_controle%` », faisait donc déclarer les trois canaux **supportés**. Le moteur aurait
   accepté une requête à références et les aurait **jetées en silence** — exactement ce que le
   critère 7 bis existe pour empêcher, réintroduit par une ligne de documentation. Les canaux
   se lisent maintenant dans les **nœuds** seuls, et deux tests le gardent.

**La seconde moitié de la bascule VRAM manquait, et elle est livrée DÉSARMÉE.** Le plan de
série décrit « déchargement du LLM → génération → le modèle d'image est déchargé » ; Angelith
faisait la première moitié seulement, laissant **12 083 Mio** occupés après un run — un
`run.py` lancé derrière trouvait la carte prise. Le mécanisme est ajouté
(`illustration.vram.decharger_image`), et **il est désarmé par défaut** : sur **sept** appels à
`/free` de ComfyUI, **un a fait segfauter le serveur** (`0xC0000005` dans son propre
`comfy/model_management.py:model_unload`, ROCm 7.14 / Windows). Le plantage est chez ComfyUI et
ne coûte aucune image — elles sont écrites et marquées avant —, mais le dépôt livre désarmé ce
que la mesure ne soutient pas, comme `manga.onomatopees.effacement.mode` au lot 22. La commande
manuelle est dans `docs/COMMANDES.fr.md` (⚠ `Invoke-RestMethod`, pas `curl.exe` : sous
PowerShell 5.1 le corps JSON n'arrive pas jusqu'à ComfyUI).

**Deux améliorations qui découlent du réel :** les canaux sont vérifiés **avant** la bascule
VRAM — refuser après avoir déchargé le LLM et chargé 12 Go coûtait plusieurs minutes pour une
erreur connue d'avance ; et le déchargement LLM ne compte plus deux fois le même modèle
(`modeles.traducteur` et `manga.modeles.manga_traducteur` nomment le même `yume-27b`), ce qui
ramène la bascule de **4,2 s à 2,1 s**, mesuré.

#### Le résultat négatif du lot, et il est mesuré

**Les images produites ne sont pas dans le registre graphique du tome, et l'écart est chiffré**
avec l'outil du lot 23 (`core/illustrations.py:signature`) :

| Descripteur | Tome (16 illus.) | Généré (11 img.) | Écart |
|---|---:|---:|---:|
| saturation moyenne | 0,0661 | 0,3231 | 0,257 |
| contraste | 0,2421 | 0,1481 | 0,094 |
| densité de trait | 0,2664 | 0,0522 | 0,214 |
| part d'aplats | 0,3669 | 0,6016 | 0,235 |
| régime de couleur | **noir et blanc** | **couleur** | ✗ |

**Écart moyen 0,200**, et un régime de couleur qui ne correspond pas du tout : le tome est au
trait, les générations sont photographiques. Ce n'est pas une surprise — c'est la moitié
« registre graphique » que le `README-ILLUSTRATION-23-27` §4 quater annonçait — mais elle est
désormais **mesurée** au lieu d'être pressentie, et c'est la matière du `PLAN-25`.

⚠ Au passage, la signature stockée par le lot 23 se **recalcule à l'identique** (0,0661 /
0,2421 / 0,2664 / 0,3669) : sa mesure est reproductible.

#### Ajouté

- `illustration/workflows/` — deux graphes au format API, leur `README.md` avec les mesures.
- **16 tests neufs** (3 454 → **3 470** collectés), dont deux qui gardent les workflows
  réellement livrés — ils doivent refuser `references`, `entites` et `image_controle` — et
  trois qui figent le déchargement de VRAM et son défaut désarmé.
- `docs/mesures/connecteur-qwen-2026-08-29.md` — les trois étapes du `PLAN-24` enfin mesurées,
  les six défauts, l'écart de style, et ce que la mesure ne dit toujours pas.

#### Modifié

- `illustration/poids.py`, `illustration/comfyui.py`, `illustration/requete.py`,
  `illustration/orchestrateur.py`, `core/bible.py` — les cinq correctifs ci-dessus.
- `config.yaml` — `illustration.comfyui.workflow` pointe le workflow vérifié ;
  `illustration.image.pas` / `guidage` passent à 4 / 1.0 pour lui correspondre, avec la note
  qui dit que ces deux valeurs **appartiennent au workflow** et ne sont pas libres.

#### Ce que ce lot ne fait toujours pas

- Il ne conditionne sur **aucune image de référence** : les workflows livrés sont
  texte-vers-image, et le moteur **refuse** explicitement le canal `references`. L'identité du
  personnage reste le `PLAN-25`.
- Il ne mesure ni `stable-diffusion.cpp` ni `diffusers`.
- Il ne corrige pas le registre graphique : il le **mesure**, et publie l'écart.

## [2.15.0] - 2026-08-29

### MINEUR — Le socle génératif : une quatrième brique, une frontière testée, un marquage sans interrupteur

> **Rien n'est périmé, rien n'est à supprimer.** Les 21 clés ajoutées sont sans effet tant que
> `illustration.actif` vaut `false`, ce qui est le défaut livré. `run.py` et `run_manga.py`
> sont **iso-comportement** : aucun de leurs fichiers n'est touché, aucun poids n'est
> téléchargé, `manga/checkpoints.py:STAGES` et `FORMAT_VERSION` sont inchangés, et la brique
> n'écrit ni ne lit sous `.checkpoints/`.
>
> Empreinte SHA-256 de `config.yaml` après le lot :
> `d611609985d53c51fd8ef6b75b3acaf1d4ad9fd0b99324c78dd4e2ee5d1e9910`.

**Une quatrième brique — `run_illustration.py` — qui produit des images NEUVES, et ne touche
aucun pixel de l'œuvre.** Elle lit `media/` et la bible visuelle du lot 23, elle écrit sous
`build/<Projet>/<Tome>/illustrations/`, elle ne composite rien dans une planche ni dans une
page. Les quatre occurrences du principe « l'IA ne dessine jamais » dans le code restent
vraies **mot pour mot**.

**La portée du principe est écrite pour la première fois, et elle ne le renégocie pas**
(décision d'Alexandre du 2026-08-27, écrite dans `docs/README.fr.md` §12, dans l'interdit n° 3
de `docs/plans/00-CONTEXTE-AGENT.md` et dans `docs/ai-provenance.md`) :

> Le principe porte sur les **pixels de l'œuvre** : aucune écriture non déterministe dans une
> planche, une page ou un fichier source. Une brique qui ne modifie **aucun** fichier existant
> n'entre pas dans son périmètre : elle produit des fichiers neufs, dans un dossier qui lui est
> propre, marqués comme générés, et supprimables sans rien casser. L'effacement de pixels
> existants, lui, reste interdit hors du cadre que le lot 22 a défini.

⚠ **Cette portée n'est pas un précédent pour le lot 22**, qui portait bien sur des pixels de
l'œuvre et qui a tranché **contre** le modèle génératif. Les trois endroits où elle est écrite
le disent.

**Et elle est vérifiée à l'exécution, pas seulement affirmée.** `illustration/frontiere.py`
remplace `open`, `Path.write_*`, `os.replace/rename/remove`, `shutil.move` et `Image.save` pour
la durée du run et lève sur toute cible hors du dossier de la brique. Un run complet sur un
tome témoin laisse **toutes** les empreintes SHA-256 préexistantes inchangées — 0 fichier
modifié, 0 supprimé — y compris le `RAPPORT.md`, le `perf.log` et le `.checkpoints/` du tome.
C'est la transposition, pour une brique entière, du `paint = paint & region.mask` de
`clean.py` : l'invariant ne doit pas dépendre d'un raisonnement.

**Le run a deux phases et un humain entre les deux.** La phase 1 écrit `requete.yaml` — un YAML
commenté, éditable, avec `valide: false` ; la phase 2 **refuse de démarrer** tant qu'il n'est
pas passé à `true`, refuse un `validation.par` vide avec un **autre** motif, et il n'existe
**aucune** clé de configuration, aucun drapeau et aucun mode « tout automatique » qui contourne
l'une ou l'autre. Un test relit `CLES_CONNUES` et échoue si une clé `illustration.*` se met à
contenir « valide », « force », « automatique » ou « skip ». Le sidecar de chaque image porte
qui a validé, quand, et le prompt **avant** et **après** sa correction.

**Le marquage AI Act n'a pas d'interrupteur.** Art. 50(2), applicable depuis le **2026-08-02**,
consulté le 2026-08-27 : les sorties d'un système générant des images de synthèse doivent être
marquées dans un format lisible par machine. Chaque PNG porte sept champs `tEXt`
(`AIGenerated=true`, graine, modèle, prompt tronqué, identifiant local, avertissement) et un
manifeste `<image>.png.provenance.json` qui archive le **payload JSON exact** envoyé au moteur.
Le garde est dynamique : tout fichier d'extension image est refusé hors de
`frontiere.ecriture_marquee()`, dont `marquage.ecrire` est le seul appelant. **Ce n'est pas un
avis juridique** — la lecture retenue est datée, sourcée et signalée à confirmer dans
`docs/ai-provenance.md`. **C2PA n'est pas fait, et c'est écrit** : un manifeste signé demande
une autorité de certification, donc une identité publiée, alors que rien ne quitte la machine.

**Le nom de l'œuvre n'entre nulle part** — ni dans le PNG, ni dans le sidecar, ni dans le
rapport de la brique : un identifiant local `oeuvre-<12 hexa>` suffit. Un prompt qui nomme
l'œuvre fait **lever** l'écriture plutôt que d'être censuré : retirer le titre en silence
changerait le prompt archivé, donc casserait le rejeu.

**Trois des quatre mesures que le plan demandait n'ont pas pu être faites**, et le lot l'écrit
dans le comportement du logiciel plutôt qu'en note de bas de page — la session n'avait ni la
7900XT ni le réseau :

- **les trois chemins d'exécution ne sont pas chronométrés** → `illustration.moteur` vaut
  `"factice"` par défaut (un carré uni de 64 × 64 dont la couleur dérive de la requête entière),
  et `ETAT_BRIQUES["illustration"]` vaut **`"experimental"`**, un mot neuf dans ce dépôt et plus
  bas que `beta`, avec sa réserve nommée ;
- **les licences de poids ne sont pas revérifiées à la source primaire** → **aucune URL et
  aucune empreinte de poids n'est codée en dur**, à l'inverse de `manga/models.py` ;
  `illustration_models/README.md` reproduit le tableau du 2026-08-27 avec « non revérifié » sur
  chaque ligne ;
- **la reproductibilité d'un backend réel n'est pas mesurée** → `--rejouer` est livré, compare
  les SHA-256, et son message dit explicitement qu'un écart n'est pas forcément un défaut.

**Deux prémisses du plan sont corrigées ici plutôt qu'en silence.** « ~10 Go en 4 bits » compte
le **transformeur seul** : les GGUF publiés donnent Q4_0/Q4_K_S à **11,9–12,3 Go** et Q4_K_M à
**13,1 Go**, encodeur de texte et VAE non comptés — et la VRAM résidente totale n'a de chiffre
nulle part. Et la description du graphe d'imports du dépôt était **fausse sur deux lignes sur
cinq** : `manga` importe `pipeline` (2 sites), `gui` importe `pipeline` (6 sites). Aucune de ces
arêtes ne crée de cycle. `tests/test_imports_briques.py` protège désormais le graphe **réel**
pour les six paquets — aucun test ne le couvrait avant ce lot, alors que « sans cycle » est un
argument de dossier de financement.

**Un arbitrage entre deux demandes du plan, écrit pour qu'il ne se redécouvre pas.** L24.6
demandait une section dans le `RAPPORT.md` du tome ; le critère 1 bis interdit d'écrire dans un
fichier préexistant. La frontière gagne — un garde qui a une exception n'est pas un garde — et
la brique écrit son **propre** `RAPPORT.md` et son propre `perf.log`, avec le contenu demandé, y
compris le coût de la bascule VRAM rapporté au prix moyen d'une image.

**La VRAM ne porte jamais les deux modèles.** La bascule appelle `core/power.py:ollama_unload`
— mécanisme **existant**, déjà utilisé avant détection/OCR — une fois par run, jamais une fois
par image ; le rechargement du LLM appartient à l'appelant, comme pour la détection.

**Et la seule mesure que la session pouvait faire a trouvé un défaut.** `core/cli.py:
models_in_config` dédoublonne **dans** une section, pas **entre** deux : la config livrée nomme
le même `yume-27b` dans `modeles.traducteur` et dans `manga.modeles.manga_traducteur`. Relevé
le 2026-08-29 sur un Ollama joignable, `yume-27b` chargé : **4,22 / 4,14 / 4,05 s** à deux
appels contre **2,03 s** à un seul, pour un résultat identique. La bascule dédoublonne donc par
`dict.fromkeys`, et un test le fige. ⚠ 2,0 s reste un **plancher** : le chargement du modèle
d'image et le rechargement du LLM ne sont pas mesurés.

#### Ajouté

- `illustration/` : `frontiere.py` (périmètre d'écriture armé pendant le run), `moteur.py`
  (l'interface, les cinq canaux, la `Requete` gelée, `MoteurFactice`), `requete.py`
  (`requete.yaml` et la porte humaine), `marquage.py` (le seul chemin qui écrit un PNG),
  `poids.py` (téléchargement repris sur coupure par `Range`, `auto=False` par défaut),
  `comfyui.py` (un client HTTP, pas un framework), `orchestrateur.py`, `rapport.py`.
- `run_illustration.py` — `--check [--telecharger]`, `--phase prompt|image`, `--rejouer`,
  `--ecraser`, `--graine`, `--personnage`.
- Bloc `illustration:` dans `config.yaml` (21 clés, toutes sans effet par défaut),
  `illustration_models/README.md`.
- `tests/test_imports_briques.py` — le graphe d'imports des six paquets, et l'absence de cycle.
- **110 tests neufs** (3 344 → **3 454** collectés), dont **aucun ne demande de GPU ni de
  poids** : tout passe sous `pytest -q -m "not modeles and not lent"`.
- `docs/mesures/socle-generatif-2026-08-29.md` — les treize critères du plan un par un, dont
  **deux non tenus** pour une seule cause, et sept points sur ce que la mesure ne dit pas.

#### Modifié

- `core/version.py` — quatrième entrée dans `ETAT_BRIQUES`, état `"experimental"` et sa réserve.
- `core/config_schema.py` — les 21 clés déclarées, cinq contraintes de valeur.
- `.gitignore` — `*.gguf`, `*.safetensors`, `*.ckpt`, `*.part`, `illustrations/`, ajoutés **dans
  le même commit** que le module de téléchargement.
- `docs/README.fr.md`, `docs/plans/00-CONTEXTE-AGENT.md`, `docs/ai-provenance.md` — la phrase de
  portée, datée et attribuée.
- `tests/test_version.py` — la quatrième brique, la liste des états admis, et un test qui échoue
  si `illustration` passe en `beta` avant que le moteur réel n'ait été mesuré.

#### Ce que ce lot ne fait pas

- Il ne prétend **rien** sur la ressemblance d'un personnage, sa nouveauté ou sa distance de
  style : ce sont les trois grandeurs du `PLAN-25`.
- Il n'insère aucune image dans un DOCX, EPUB ou PDF (`PLAN-27`), n'affine aucun modèle, et
  n'appelle aucun LLM — le prompt de la phase 1 est un assemblage **déterministe** des attributs
  cités de la bible ; le faire rédiger par `yume-27b` est le `PLAN-26`.
- Il ne touche ni `manga/clean.py`, ni `manga/typeset.py`, ni `manga/effacement.py`, ni leurs
  tests, ni aucun fichier de `pipeline/`, `scan/` ou `gui/`.

## [2.14.2] - 2026-08-29

### CORRECTIF — la figure du dépôt se compare en PIXELS, pas en octets de PNG

**Le défaut, et il est hérité du lot 22.** `tests/test_banc_effacement.py::
test_la_figure_du_depot_est_a_jour` comparait `docs/img/effacement-2026-08-28.png` à une
régénération **octet par octet**. Il passait sous `windows-latest` et échouait sous
`ubuntu-latest` **depuis que la figure existe** — la matrice à deux systèmes date du lot 20,
la figure et le test du lot 22. L'écart portait sur la **longueur du bloc IDAT** : une
différence de compression zlib entre les deux runners, pas une différence de dessin. Comparer
un encodage revient à tester la version de zlib du runner, ce que ce test ne veut pas dire.

**Et les pixels ne peuvent pas diverger — c'est mesuré, pas supposé.** `figure_synthetique`
n'ouvre aucune police, ne tire aucun aléa, et son seul appel transcendant est `6·sin(x/37)`
dans le fond « aplat », converti en `uint8` par **troncature**. Sur la grille réelle
(150 × 260) :

| Mesure | Valeur |
|---|---|
| valeurs exactement entières | **150**, toutes en `x = 0`, où `sin(0) = 0` est exact sur toute plateforme IEEE |
| plus petite partie fractionnaire non nulle | **9,27 × 10⁻⁶** |
| plus petite distance sous un entier | **3,13 × 10⁻⁵** |
| 1 ULP au voisinage de 242 | ~**2,8 × 10⁻¹⁴** |

**Neuf ordres de grandeur** séparent l'imprécision possible d'un `sin` de la marge nécessaire
pour faire basculer une troncature. Aucune implémentation de `sin` ne peut changer un pixel.

Vérifié en réencodant la figure publiée à trois niveaux de compression zlib (0, 1, 9) :
**les octets diffèrent à chaque fois — de 7 156 à 729 808 contre 8 090 —, les pixels jamais.**

Le test compare donc les pixels, et son message d'échec dit maintenant **combien** de pixels
diffèrent et **de combien de niveaux** — un diff d'octets compressés ne l'apprenait à personne.
L'identité au bit près reste vérifiée là où elle a un sens : deux exécutions sur la même
machine, par `test_la_figure_se_refait_a_l_identique`, qui prouve l'absence d'aléa et de police.

⚠ **La figure publiée n'est pas régénérée** : ses pixels sont justes. La régénérer sous
Windows aurait continué d'échouer sous Linux, et l'inverse.

---

## [2.14.1] - 2026-08-29

### CORRECTIF — `docs/` rangé : les mesures d'un côté, les procédures de l'autre

> **Aucun changement de comportement.** Des fichiers déplacés, des liens réécrits, cinq
> documents neufs. `ruff check .` passe, la suite passe — **3 284 passés, 3 ignorés,
> 57 désélectionnés**.

**Le constat.** La racine de `docs/` portait 22 fichiers dans lesquels un compte rendu daté du
lot 16, le mémo des commandes et le protocole du banc se lisaient au même niveau. Rien ne
distinguait ce qui se périme de ce qui fait référence.

**Trois dossiers, une règle par dossier.**

- **`docs/mesures/`** — les 15 comptes rendus datés, un par lot livré, plus les relevés hors
  lot (`seuils-affinage-detecteur.md`, `inventaire-couplage-fr.md`, `sonar-2026-08-26.md`).
  Un `README.md` les indexe et rappelle la règle qui les régit.
- **`docs/procedures/`** — **neuf** : une fiche courte par brique, avec les commandes dans
  l'ordre où on les lance, **les clés de `config.yaml` qui en changent le résultat**, et une
  section « quand ça ne marche pas » : `light-novel.md`, `manga.md`, `scan-ocr.md`,
  `interfaces.md`, `bible-visuelle.md`. `banc-de-mesure.md` les rejoint — c'est un protocole,
  pas une mesure.
- **La racine de `docs/`** ne garde que les fichiers de référence : `README.fr.md`,
  `COMMANDES.fr.md`, `PUBLICATION-ANGELITH.md`, `roadmap.md`, `ai-provenance.md`,
  `chiffres-de-reference.md`.

**Les liens ont été réécrits, pas laissés à pourrir.** 45 fichiers portaient un chemin vers un
document déplacé — code, tests, CI, `config.yaml`, plans. **Tous les liens Markdown relatifs du
dépôt résolvent** : vérifié en repartant du disque, fichier par fichier. Trois liens **déjà
cassés avant ce rangement** sont réparés au passage (`docs/README.fr.md` → `CHANGELOG.md`, et
deux chemins d'outil dans `banc-de-mesure.md`).

**Deux garde-fous ont été mis à jour, parce qu'un rangement ne doit pas les désarmer :**

- `tools/verifier_livraison.py` cherchait `^docs/banc-*.md`. Il accepte maintenant
  `docs/mesures/banc-*.md` **et garde la racine sous surveillance** — un banc rangé au mauvais
  endroit doit être jugé, pas ignoré ;
- `tests/test_coherence_chiffres.py` cherche les tableaux de banc aux deux niveaux, pour la
  même raison. Le rendre aveugle au nouveau dossier aurait désarmé la règle « aucun lot ne se
  termine sans un tableau daté » au premier rangement.

`docs/plans/00-CONTEXTE-AGENT.md` §9.6 dit désormais `docs/mesures/<sujet>-<date>.md` : c'est
la convention que les prochains lots doivent suivre.

### CORRECTIF — les titres d'œuvre du lot 23, remplacés par des désignations neutres

`tools/verifier_arbre.py` signalait **11 titres d'œuvre en clair** dans les fichiers livrés au
lot 23 — `docs/mesures/bible-visuelle-2026-08-29.md` surtout, mais aussi `core/illustrations.py`
et les tests. La règle de `docs/PUBLICATION-ANGELITH.md` veut une désignation neutre, et elle
est vérifiée par un outil : elle n'était pas tenue. Le document et le code emploient maintenant
`roman A` … `roman M`, `manga A`, `webtoon A`, avec une légende qui dit que **ces étiquettes
sont locales au document** — le dépôt ne tient pas de registre global, et c'est délibéré.

**Seule exception, et elle est écrite : *Pride and Prejudice*, domaine public**, la seule œuvre
dont une image aurait le droit de figurer dans un document de ce dépôt.

---

## [2.14.0] - 2026-08-29

### MINEUR — La bible visuelle : le dépôt sait enfin à quoi ressemble un personnage

> **Rien n'est périmé, rien n'est à supprimer.** Aucune clé n'est ajoutée à `config.yaml`,
> aucun cache n'est touché (`manga/checkpoints.py:STAGES` et `FORMAT_VERSION` inchangés), la
> bible n'entre **jamais** dans le prompt du traducteur, et un tome relancé sans rien toucher
> rend exactement la même sortie. Le seul champ qui peut traverser vers la traduction est
> `genre`, et seulement par le geste explicite `tools/bible.py --revue --ecrire-genre`.

**Le constat mesuré.** Sur les **326 personnages** des **14 `glossaire.yaml` vivants**
(2026-08-29), **326 ont un `role` vide — 100 %** et **144 n'ont pas de genre — 44,2 %**, alors
que `core/glossary.py` étiquette lui-même cette catégorie « Personnages (le genre commande les
accords) ». Et **446 illustrations dorment dans 15 dossiers `build/*/*/media/`** sans que rien
ne les relie aux personnages. Tout est dans **`docs/mesures/bible-visuelle-2026-08-29.md`**.

**Ce qui est livré.**

- **`core/illustrations.py`** — inventaire, classement (couverture / pleine page / double page /
  vignette / indéterminée), rattachement au chapitre, et **signature de style** du tome
  (palette, saturation, contraste, densité de trait, part d'aplats), tout en numpy et Pillow,
  sans Qt et sans OpenCV. **317 des 446 fichiers sont exploitables — 71,1 %.**
- **`core/bible.py`** — `sources/<Projet>/bible.yaml`, un fichier SÉPARÉ du glossaire :
  y ajouter un champ ferait entrer l'apparence dans le prompt du traducteur, donc changerait
  le caractère de la traduction de tous les tomes (règle MAJEUR).
- **`core/bible_texte.py`** — passe lexicale déterministe (les passages candidats) et **indice
  de genre**, mesuré à **26 concordances sur 26** contre les genres déjà déclarés du corpus,
  **zéro contradiction**, pour un rappel de 24,8 %.
- **`core/bible_llm.py`** — les deux passes modèle, et surtout **ce que le code leur refuse**.
- **`tools/bible.py`** — `--inventaire`, `--signature`, `--proposer`, `--revue`, `--rapport`.
- **Prompt neuf : `langues/fr/prompts/bible_apparence.md` et `langues/en/…`.** ⚠ **Absent de
  `core/langues.py:PROMPTS_REQUIS`**, comme `manga_relecteur.md` : l'y mettre invaliderait au
  démarrage tout pack tiers écrit avant ce lot. Ce prompt ne touche à aucune traduction.

**La règle non négociable, et elle est dans le code.** *Un attribut sans `citations[]` n'entre
pas dans la bible.* `bible.save` retire un attribut non cité au lieu de le signaler, et rend la
liste de ce qu'il a retiré.

**Le cas mesuré qui justifie les garde-fous.** Sur un lot de 25 passages de roman D, `yume-27b`
est parti en boucle : `Gomuji | age_apparent | dix-huit ans` répété avec un numéro de passage
incrémenté **de 26 à 50**, hors du lot fourni. Sans le contrôle de plage, l'attribut serait
entré **25 fois** avec **25 citations fabriquées**. Le code en a refusé 25 sur 25.

**Trois résultats négatifs, écrits plutôt que corrigés en silence.**

1. **Un critère du plan est retiré.** Classer en vignette toute image de « moins de 3 couleurs
   dominantes » range **48 des 446 fichiers (10,8 %)** — des planches au trait noir sur blanc —
   parmi les logos. Retiré du classement, gardé comme mesure.
2. **Le critère « résoudre 30 genres sur 150 » est hors d'atteinte**, et le plafond est **15** :
   **129 des 144** manques sont dans des projets sans texte traduit **ni** illustration
   extraite, dont **106 pour le seul manga A**, dont le `build/` est vide.
3. **La sonde vision tombe dans la zone grise du plan** — 6 descriptions exactes, 5 partielles,
   1 fausse sur 12. La passe est donc livrée **sans autorité** : sa sortie ne va que dans
   `bible.propositions.yaml`, avec `confiance: 'llm'`, et rien n'entre dans `bible.yaml` sans
   un `o` humain. Abstention mesurée : **26 sur 35** appels vision.

**Un déplacement de module, prouvablement neutre.** `core/` n'a pas le droit d'importer
`pipeline/` (deux tests le vérifient) et `core/illustrations.py` avait besoin du même analyseur
de marqueurs. Le contrat du marqueur `<!-- IMG: … -->` descend donc dans le socle,
**`core/marqueurs.py`** : `IMG_MARKER`, `make_marker`, `split_marker`, `strip_images`,
`orphan_markers`, `manifest_for_chapter`. `pipeline/extract.py` et `pipeline/images.py` les
réexportent sous leurs noms d'origine, et `tests/test_images.py` vérifie l'**identité d'objet**
— comme le lot 2.1 pour les alias `pipeline.x` → `core.x`.

---

## [2.13.0] - 2026-08-28

### MINEUR — Effacer et redessiner : le principe est confirmé, l'effacement est déterministe

> **Rien n'est périmé, rien n'est à supprimer.** Les huit clés ajoutées sont désarmées, `sfx`
> reste hors du graphe d'invalidation (`checkpoints.CACHE_NON_BLOQUANT`), `FORMAT_VERSION`
> vaut toujours 3, et un tome relancé sans toucher `config.yaml` rend des planches
> **identiques au bit près** — vérifié par un test.

**La décision d'architecture, prise et écrite avant le code.** `PLAN-22` était le seul plan
autorisé à renégocier « l'IA ne dessine jamais » (README §12). **Il l'a refusé**, et le
principe reste écrit en cinq mots. Trois raisons mesurées, dans l'ordre où elles pèsent :

1. **le garde-fou du lot 21 rend le modèle inutile aujourd'hui** — un effacement n'est permis
   que sur une zone `lecture_sure`, et ce taux est de **0 % sur les six tomes** du corpus ;
2. `Qwen-Image-Edit` fait **20 milliards de paramètres** (Apache-2.0, vérifié) là où la
   contrainte écrite du projet est déjà « 27 milliards sur un GPU grand public », occupé par
   le traducteur ;
3. **la licence des poids `big-lama` n'a pas pu être établie sur une source primaire** — le
   dépôt porte déjà deux poids sous contrainte, un troisième serait indéfendable.

Écrit dans `docs/README.fr.md` §12, `README.md` et `docs/ai-provenance.md`.

**Ce qui est livré à la place est déterministe** — `manga/effacement.py`. Masque d'encre dilaté
rempli par la couleur de fond mesurée au lot 21, ou reconstruit par **diffusion** (itération de
Jacobi sur l'équation de Laplace, numpy pur, aucune dépendance ; pas d'OpenCV). C'est le mode
« texte » de `clean.py` transposé hors de la bulle.

**Un chiffre du plan de lot est faux, et il est corrigé ici plutôt qu'en silence.** Le plan
posait qu'au-dessus de 0,60 d'uniformité « un remplissage de couleur unique serait correct ».
Mesuré sur les 2 455 zones des six tomes (`tools/banc_effacement.py`), la couture rapportée au
grain naturel du fond — 1,0 = se raccorde comme le fond se raccorde à lui-même :

    tout uniforme   2,78   · sur le seul palier ≥ 0,60 : 2,43
    tout diffusion  0,89   · sur le seul palier ≥ 0,60 : 0,84

Le remplissage plat laisse une arête deux fois et demie plus franche que celle que le dessin
porte, **y compris là où le fond est réputé uni**. `methode: "diffusion"` est donc le défaut, et
le seuil de 0,60 survit sous `methode: "auto"` pour qui veut le revérifier.

**Et le résultat honnête du lot : sur le corpus d'aujourd'hui, l'effacement efface zéro zone.**
Le taux de `lecture_sure` est de 0 % faute de seconde voie de lecture — `manga.onomatopees.
concordance` exige un serveur LLM vision, injoignable au lot 21. Le chemin est complet, testé,
et sans effet tant que cette condition n'est pas remplie. `RAPPORT.md` le dit zone par zone.

**Ajouté**

- `manga/effacement.py` — l'effacement déterministe. Rend un **calque**, ne mute jamais la
  planche, et n'écrit **jamais** un pixel hors de la boîte d'une zone. Il refuse trois
  situations, et les compte toutes : lecture non concordante, style non mesuré, fond sous le
  seuil d'abandon (0,35 — **260 zones sur 2 455**, le palier du gratte-ciel de la page 44).
- `manga.onomatopees.effacement` — six clés. `mode` vaut `"aucun"` (défaut), `"calque"` (le
  PSD porte un calque `Effacement SFX` masquable, **`pages_out/` n'est pas touché**) ou
  `"aplati"` (le seul mode qui change un pixel de sortie).
- **PSD** (`manga/psd.py`) — quatre piles neuves, toutes optionnelles : `Effacement SFX`
  masquable au-dessus du fond, `Glose NN`, `SFX NN` nommée avec sa traduction, et un calque
  **vide** `SFX ? NN` par zone illisible, avec sa position. Le letteur voit *où* intervenir au
  lieu de rouvrir la planche. Les gloses n'existaient jusqu'ici **que** dans le composite
  aplati — `fond_propre` est capturé avant le rendu — et c'était un défaut, pas une décision.
- **Lettrage hors bulle** (`manga/typeset.py`, L22.3) — trois capacités, toutes neutres par
  défaut : masque de découpe **dissocié** de la zone d'habillage (`BubbleStyle.decoupe`, `None`
  pour toute bulle) ; **rotation** du calque (`Fit.angle`, `0.0` pour toute bulle) ; **contour
  réglable** (`contour: "toujours"` / `"jamais"`, `contour_epaisseur_sfx`). Les garde-fous de
  `best_fit` sont **paramétrés par type de zone**, pas contournés.
- `tools/banc_effacement.py` — le banc : empreinte, résidu, couture rapportée au grain, par
  palier d'uniformité, plus `--dilatation` / `--passes` / `--seuil-uniformite` pour balayer et
  `--synthetique` pour la figure avant/après publiable.
- `docs/mesures/relettrage-2026-08-28.md` et `docs/img/effacement-2026-08-28.png`.

**Corrigé**

- `manga/text_detection.py` — la docstring annonçait que le texte trouvé est « traduit puis
  **glosé** à côté, par `typeset.py` ». Le mot `glose` n'apparaît **nulle part** dans
  `typeset.py` : le dessin se fait dans `manga/gloss.py`. Elle annonçait aussi l'effacement
  « délibérément écarté » sans distinguer le modèle génératif — refusé — du déterministe, qui
  existe désormais et reste désarmé.

**Ce que le lot ne fait pas** — aucun corps variable par glyphe, aucune déformation, aucun
texte sur courbe ; aucun effacement dans le chemin par défaut ; aucun effacement d'une zone
dont la lecture n'est pas concordante ; aucun changement au traitement des **bulles** —
`tests/test_manga_clean.py` n'est **pas modifié d'une ligne** et passe.

---

## [2.12.2] - 2026-08-28

### CORRECTIF — Second lot Sonar : 2 complexes, 18 autres, et trois outils sortis de 0 %

Nouvelle extraction après le scan du lot précédent (184 issues ouvertes ; le `S930` de
`run_ocr.py` et le `S3776` de `scan_volume` en sont bien partis). Le tirage vise cette fois
la NOTE plutôt que le hasard : les cinq bugs d'abord — ils fixent à eux seuls la note de
fiabilité —, puis les familles dont l'équivalence se prouve.

**Les cinq bugs (`Reliability`).**

- `manga/rendu.py` — `fits = [] if avec_fits else []` rendait la même valeur dans les deux
  branches (`S3923`), reste de l'époque où le second cas valait `None`.
- `manga/gloss.py` — `abs(dx) == 1.0` sur des coordonnées d'ancrage (`S1244`, deux fois). Le
  test était juste, les valeurs venant d'un littéral du module ; mais la première coordonnée
  issue d'une division ferait basculer un ancrage de bord en ancrage relatif, en silence.
- `manga/quality_manga.py` — le `$` n'était écrit que dans une branche de l'alternative
  (`S5850`). La portée était déjà la bonne ; elle est maintenant explicite, à équivalence
  vérifiée sur les dix formes que le module rencontre, « 1972... » compris.
- `tests/test_manga_recuperation.py` — une assertion qui comparait deux expressions
  identiques (`S5863`). Le test porte sur la relecture, pas sur une tautologie : les deux
  lectures sont nommées, et il le dit.
- `manga/typeset.py` — `harmonize` rendait `fits`, c'est-à-dire son propre argument, par ses
  deux chemins de sortie (`S3516`, BLOCKER). Une valeur de retour qui ne peut pas varier
  invitait à écrire `fits = harmonize(fits, cfg)` comme si la liste d'origine restait
  intacte ; aucun des cinq appelants ne s'en servait.

**Six expressions régulières de `core/glossary_build.py` (`S8786`).** Elles rognaient la
sortie du LLM en chemin — `(.+?)\s*`, `(.{1,60}?)\s+` — ce qui fait de `.` et de `\s` deux
façons d'absorber le même espace : le moteur doit essayer chaque partage avant de conclure,
sur un texte dont rien ne borne la longueur. Le rognage passe en Python, chez des appelants
qui le faisaient déjà. `tests/test_glossary_build_motifs.py` compare chaque forme neuve à la
forme d'origine sur un corpus des cas observés — 230 assertions — et garde qu'aucune des
trois écritures fautives ne revienne.

**Trois littéraux triplés de `pipeline/orchestrator.py` (`S1192`).** `- (rien à signaler)`
est une valeur SENTINELLE : écrite au cache, relue, comparée, et servant de charge utile de
dry-run. Cinq copies littérales d'une chaîne dont l'égalité compte — accent inclus.

**Les deux complexes (`S3776`), et pourquoi ceux-là.**

- `core/glossary_build.py > parse_notes` (109) — la chaîne de neuf `elif` sur les champs
  sort en `_appliquer_champ`, les trois garde-fous de nom en `_nom_et_champs_implicites`, et
  les deux branches courtes en `_anglicisme` / `_groupe`.
- `pipeline/extract.py > _extract_pdf` (89) — ses deux passes étaient déjà nommées par ses
  commentaires ; la troisième, l'émission, y était noyée.

> ⚠ **Les deux plus gros ont été écartés, et c'est un choix.** `_process_volume`
> (1 993 lignes, complexité 657) et `process_volume` (977 lignes, 332) sont les deux
> orchestrateurs. Les refondre au milieu d'un lot de vingt correctifs, c'est mettre en jeu
> des heures de GPU sur un tome pour un gain de note. Ils demandent un lot à eux seuls.

**Les trois `S2083` (BLOCKER) : traités à la source, résultat non vérifiable d'ici.** La
tentative du lot précédent — vérifier le chemin DÉRIVÉ — ne les avait pas fait tomber : le
puits reste teinté tant que le nom d'œuvre l'est. `core.chemins.segment` valide donc le nom
LÀ OÙ IL ENTRE (`process_volume`, `import_into_project`, `reintegrer_dans_projet`). C'est un
vrai garde-fou, et sa cible n'est pas un attaquant mais le collage : « sources/Mon LN » copié
depuis un explorateur au lieu de « Mon LN » ferait partir la sauvegarde du glossaire ailleurs
que là où l'utilisateur croit. Que l'analyse de teinte de Sonar l'accepte comme rupture de
chaîne ne se vérifie qu'au prochain scan.

### CORRECTIF — Couverture : trois outils passent de 0 % à ~96 %

`sonar.sources` inclut `tools/`, et huit de ces scripts n'étaient couverts par rien. Les
trois plus gros qui se testent sans modèle ni interface le sont désormais — et pas pour le
chiffre : chacun portait un invariant que son propre module déclare important.

| Module | Avant | Après | L'invariant que les tests tiennent |
|---|---|---|---|
| `tools/sonar_issues.py` | 0 % | 99 % | la pagination ne s'arrête jamais en silence ; les hotspots ont leur endpoint |
| `tools/verifier_ordre.py` | 0 % | 95 % | `--corriger` est une permutation : corrections manuelles et mises en page suivent leurs bulles |
| `tools/compter_variantes.py` | 0 % | 96 % | le français mesuré vient de `qa.json` — ce qui est DESSINÉ, pas la sortie brute du modèle |

Aucun de ces tests ne touche le réseau, ni ne lit le vrai jeton Sonar.

## [2.12.1] - 2026-08-28

### CORRECTIF — La CI Linux disait vrai, et pas seulement sur la CI

`ubuntu-latest` tombait sur 8 tests. Sept étaient des tests qui supposaient Windows ; le
huitième non — et c'est celui-là qui compte.

**La chaîne de polices du lettrage n'existait que sous Windows.** `DEFAULT_FONT_CANDIDATES`
ne contenait que `C:/Windows/Fonts/…` : hors Windows elle se réduisait à Comic Neue, qui est
une police **latine**. Le `♪` de « Moi, je préfère les filles ♪ » n'était donc pas dessiné —
il était **supprimé** de la bulle. Une planche produite sous Linux sortait amputée d'un signe
que le traducteur avait bel et bien produit, et la perte n'apparaissait que dans une ligne
`glyphes_manquants` du rapport. Même silence que celui que le lot 20 a supprimé pour la
police japonaise, à un autre endroit.

- `manga/typeset.py > POLICES_SYMBOLES` : candidats **par plateforme** — Lucida Sans Unicode
  sous Windows, **DejaVu Sans** sous Linux (aux emplacements Debian/Ubuntu, Fedora et Arch),
  Arial Unicode sous macOS. La CI installe `fonts-dejavu-core`.
- Couverture **mesurée**, pas supposée : DejaVu Sans Bold a `♪ ♫ ♥ ★ ☆ → ← ↑ ↓ ※ ♂ ♀` et n'a
  **ni kana ni `・`**. C'est la condition pour ne pas court-circuiter la table de
  substitution — une police CJK dans la chaîne ferait rebasculer un paragraphe entier de
  français pour un seul point médian. Un test garde cet invariant.
- `tests/test_manga_typeset.py` **échoue** — il ne skippe pas — quand aucune police à
  symboles n'est trouvable, avec le message de `explication_absence_symboles`.

Les sept autres : `ctypes.windll` patché par chaîne pointée (monkeypatch devait le résoudre,
donc `ModuleNotFoundError` sous Linux avant même d'entrer dans le test), et un `argv[0]`
d'essai écrit à la windows — sur Linux la contre-oblique n'est pas un séparateur, et
`Path(...).name` rendait donc la chaîne entière. Le code était juste ; c'est le chemin
d'essai qui n'avait pas de sens sur cet OS.

### CORRECTIF — Lot Sonar : 20 issues tirées au sort (graine 20)

Sur les 177 issues ouvertes de SonarQube Cloud, un tirage reproductible de 20. Une seule
était un **bug d'exécution**, et elle n'était couverte par rien :

- **`run_ocr.py --list` levait un `TypeError`** (`python:S930`). `cli.afficher_liste` porte
  un `*` : `sous_dossier` et `etat` sont keyword-only, et un `None` était passé en sixième
  positionnel. Aucun test n'exerçait ce chemin. Le garde-fou ajouté ne vise pas ce fichier
  mais la **famille** : il lie la signature à **tous** ses appelants par l'AST, parce
  qu'ajouter un paramètre keyword-only est indolore à la lecture et casse en silence
  l'appelant qui passait par la position.

Deux défauts réels se cachaient derrière les alertes de chemin (`S2083`, `S8705`, `S8707`),
dont le scénario d'attaque n'existe pas ici — la donnée « contrôlée par l'utilisateur » est
le nom d'œuvre qu'il vient lui-même de taper :

- `exists()` était pris pour « c'est un fichier ». Un **dossier** passait la garde de
  `empreinte_config`, et le `read_bytes()` suivant levait au milieu d'un banc de plusieurs
  minutes — `IsADirectoryError` sous Linux, `PermissionError` sous Windows, aucun des deux ne
  nommant le fichier attendu.
- Les chemins dérivés (sauvegarde de glossaire, temporaire d'écriture atomique) tenaient leur
  sûreté d'une propriété **implicite** de `with_name`. `core/chemins.py` en fait un invariant
  vérifié, et Pandoc n'est plus lancé sans qu'on ait vérifié que son argument est un fichier.

Le reste est neutre pour la sortie :

- **`S5754`** — `SystemExit` sert de canal d'erreur de domaine (`sys.exit("modèle
  introuvable")`) et `run_manga.py` l'avale pour ne pas perdre une série entière sur un
  chapitre. Il ne l'avale plus que **porteur d'un message** : un `sys.exit(2)` est une
  demande d'arrêt et remonte.
- **`S8786`** — deux expressions régulières de `pipeline/render.py` avaient deux
  quantificateurs illimités autour d'un littéral (coût quadratique par rétro-action).
  Réécrites par anticipation et par découpage en deux motifs, à équivalence vérifiée.
- **`S3776`** — huit fonctions au-dessus du seuil de complexité, découpées **selon les
  phases que leurs propres commentaires nommaient déjà** : `scan_volume` (39), `run_doctor`
  (35), `derives_ancrees` (26), `split_blocks` (25), `test_connection` (23), `extract_epub`
  (22), `lister_sources` (17), `elaguer` (16). Aucune règle de décision n'est touchée.
- **`S1192`** — trois noms de colonne de `tools/banc.py` cités trois fois chacun. Un nom de
  colonne y est une **clé de dictionnaire** autant qu'un en-tête : le retoucher à deux
  endroits sur trois ne casse rien de visible, la colonne se remplit simplement de vide.

⚠ **Le jeton SonarQube.** Un fichier `SONAR_TOKEN` de 40 octets vivait à la racine, **ni
ignoré par git, ni couvert** par la liste noire de `tools/verifier_arbre.py` — il ne tenait
qu'à ce que personne ne fasse `git add -A`. Déplacé vers `.sonar-token`, qui est le nom que
`tools/sonar_issues.py` lit et que les deux garde-fous connaissaient déjà ; les deux autres
noms probables y sont ajoutés.

## [2.12.0] - 2026-08-28

### MINEUR — Lot 21 : lire l'onomatopée avant de prétendre l'écrire

> ⚠ **Un seul point n'est pas iso-comportement, et le voici.** `manga.onomatopees.broderie_ratio`
> est livré **armé à 3,0** : une traduction d'onomatopée dont le rendu pèse plus de trois fois sa
> source en tokens, et au moins 8 tokens, est désormais **vidée** et signalée au rapport au lieu
> d'être écrite. Mesuré sur les 1 596 paires source/rendu déjà en cache : **6 zones concernées,
> soit 0,38 %**, et aucune n'est une traduction — ce sont six phrases inventées à partir d'un
> signe (`『あ』 → « C'est faisable. Après la diffusion vient le focalisation. »`). Sur le
> pipeline actuel, où le triage écarte déjà la ponctuation, il en resterait **4 sur 1 596**.
> `broderie_ratio: 0` rétablit le comportement d'avant, au bit près. **Tous les autres réglages
> du lot sont livrés désarmés.**

Le dépôt disait depuis la v1.0.0 que la lecture du texte hors bulle n'était pas fiable, et il
le disait avec trois exemples. Ce lot la **mesure**, sur un échantillon de 60 zones tirées au
sort (graine 21) et transcrites une par une. Le résultat est plus mauvais que la phrase, et il
tombe d'un côté du seuil que le plan avait fixé d'avance :

    lecture exacte              6   14,6 %      ← le plan : « sous 30 %, la lecture est le cœur du lot »
    lecture partielle           6   14,6 %
    PLAUSIBLE MAIS FAUSSE      21   51,2 %      ← le cas dangereux
    manifestement absurde       8   19,5 %

sur les 41 zones dont la lecture nourrit le LLM (7 filigranes ne sont jamais lues, 11 rendent
de la ponctuation traitée sans appel, 1 est écartée par le triage).

Et le détail qui décide : les 6 lectures exactes sont **4 narrations sur 9** (44 %) et
**2 onomatopées sur 14** (14 %) — les deux étant des katakana standard de deux signes.
`manga-ocr` lit la narration imprimée, qui est typographiquement du dialogue, et n'atteint
presque jamais l'onomatopée stylisée. **`mode: "rapport"` reste donc le défaut, et il le reste
désormais avec un chiffre derrière lui.**

### Quatre affirmations du dépôt ou du plan qui étaient fausses

1. **« 283 des 448 zones du Vol.1 sont des filigranes — 63 % »** (`config.yaml`,
   `manga/text_detection.py`). Faux, et réfuté par le commit qui l'a écrit : `772e5b7` porte
   à trois lignes d'écart « 92 mobilier · 15 bruit · 81 ponctuation · 260 japonais », dont la
   somme fait 448. La vraie valeur est **92 sur 448 (20,5 %)**, et **0 sur 217** pour le
   *manga B*. Un balayage complet des deux réglages du filtre ne dépasse jamais 181 zones : le
   plafond est structurel — le détecteur ne voit le filigrane que sur 47 et 45 planches sur
   150. Corrigé aux deux endroits, avec la mesure.
2. **« La DÉTECTION est fiable, c'est la lecture qui ne l'est pas. »** Faux au niveau de la
   zone. Sur les 60 : **14 onomatopées** (23 %), **16 zones sans aucun texte** (27 %),
   **14 agrégats** mêlant onomatopée, bulle et dessin dans une seule boîte (23 %), 9 narrations,
   7 filigranes. Le chiffre des agrégats est confirmé indépendamment sur tout le corpus :
   **632 zones sur 2 456 (25,7 %) contiennent au moins la moitié d'une bulle**.
3. **« La polarité codée en dur est fausse une fois sur deux. »** Faux : **13,6 %** des
   2 455 zones portent une encre claire, et la polarité mesurée est juste **55 fois sur 55**
   là où un booléen a un sens. Le vrai défaut est neuf : **5 zones sur 60 sont des glyphes
   ÉVIDÉS** (corps clair à contour sombre, ou l'inverse), dont **4 des 14 onomatopées**. Le
   booléen rend alors systématiquement la polarité du **contour**, jamais celle du corps.
4. **« Le contour d'une glose est blanc par construction, via `calque_fit`. »** Faux : les
   gloses ne passent pas par `calque_fit`. `gloss.dessiner` a toujours choisi sa polarité
   localement ; son contour est noir **ou** blanc. Le défaut réel est que ces deux pôles sont
   *purs*, et qu'un contour blanc franc sur une trame grise découpe un halo.
5. **« koharu embarque un recogniseur d'onomatopées, avec son propre jeu de caractères »**
   (`config.yaml`). Faux : son README ne liste que quatre OCR généralistes. Corrigé.

### Trois réglages livrés DÉSARMÉS, avec le chiffre qui l'explique

- **`manga.onomatopees.aire_max_frac: 0.0`** et **`remplissage_max: 0.0`** — le lot 14 avait
  nommé ce levier ; il est mesuré, et le résultat est négatif. La distribution d'aire est
  **continue** (aucun creux), et surtout la vérité terrain dit l'inverse de ce qu'on attendait :
  **le dessin pris pour du texte est plus PETIT que les vraies onomatopées** (médiane 0,8 %
  contre 3,4 %, maximum 4,2 % contre 32,3 %). Une borne haute couperait exactement ce que la
  passe existe pour trouver. Le garde-fou de forme ne discrimine pas non plus : la part d'encre
  vaut **0,457 sur les onomatopées contre 0,456 sur le dessin pur**, et reste plate (0,37 à
  0,48) dans toutes les bandes d'aire du corpus.
- **`manga.onomatopees.concordance: false`** — la seconde voie de lecture coûte un appel LLM de
  plus par planche porteuse.
- **`manga.typeset.glose_contour_mesure: false`** — ne concerne que le mode `"glose"`, qui n'est
  pas le défaut : il n'y a aucun pixel de sortie derrière ce réglage, et l'armer sur une mesure
  d'images que le lot n'a pas faite serait malhonnête.

### Ce que le lot ajoute

- **`tools/banc_sfx.py`** — le banc du texte hors bulle : triage, distribution d'aires,
  uniformité du fond local, polarité, remplissage, orientation, et un **échantillon
  reproductible** (graine écrite dans le dépôt) avec export de crops. Cache-seul, aucun modèle
  chargé ; 2 456 zones sur 6 tomes en 2 min 18 s.
- **`clean.analyser_zone_hors_bulle` / `analyser_zones_hors_bulle`** et le type
  `StyleHorsBulle` — la mesure que `analyze_regions` ne fait pas, dans une fonction **séparée**
  qui laisse intact l'alignement par position dont dépendent `ocr.json` et `traduction.json`.
  Elle mesure la polarité réelle, la couleur de l'encre, la couleur et **l'uniformité du fond
  local**, le remplissage et l'orientation — tout ce qu'un effacement exigera et qu'on ne
  pourra plus mesurer après. Réutilise la méthode de couleur déjà calibrée
  (`_couleur_de_fond`), sans en réinventer une.
- **`sfx.json` porte une clé `styles` optionnelle** qui persiste cette mesure, faite sur
  l'image d'ORIGINE. ⚠ **`checkpoints.FORMAT_VERSION` n'est PAS incrémentée** : elle encode le
  contrat de nombre et d'ordre, qu'un champ de provenance ne touche pas. Un cache écrit avant
  ce lot rend `[]`, rien ne se relance, **aucun cache n'est invalidé**. Coût mesuré :
  ≈ 0,16 s par planche porteuse, contre 1,5 s (GPU) à 139 s (CPU) pour l'inférence qui la
  précède.
- **`manga/sfx_lecture.py`** — le drapeau `lecture_sure` / `lecture_douteuse`, décidé par
  **concordance** et non par confiance (aucun de ces modèles n'expose de score exploitable).
  Seuil de similarité 0,80 et non égalité stricte, parce que deux lectures d'une même narration
  diffèrent couramment d'un signe là où deux lectures d'un dessin n'ont rien en commun. **Une
  seule voie ne concorde avec rien** et rend `douteuse` : c'est l'état réel du dépôt, et
  l'appeler « sûre » baptiserait le problème. C'est ce drapeau, et lui seul, qui autorisera
  `PLAN-22` à dessiner.
- **Voie A** — `_lire_sfx_vision` joint les crops rectangulaires bruts au modèle
  `manga_onomatopees` et lui demande une **transcription**, pas une traduction. Nouvelle
  consigne surchargeable par pack : **`manga_sfx_lecture_entete`**
  (`langues/en/pack.yaml`, défaut français dans `manga/consignes.py`).
- **Voie C** — `_exporter_crops_sfx` écrit le crop des zones douteuses dans
  `build/…/manga/sfx_illisibles/`, plafonné par `crops_illisibles`. À 14,6 % de lectures
  exactes, la transcription à la main n'est pas un repli : c'est le chemin fiable, et il
  n'était pas outillé.
- **`quality_manga.onomatopee_brodee` / `refuser_onomatopees_brodees`** et le motif
  `sfx_broderie` — cf. l'encadré en tête. Refus **par zone** et non motif de page : rejouer
  douze zones pour en corriger une paierait un appel pour reprendre onze traductions correctes.
- **`RAPPORT.md`** dit désormais les rejets de détection **par motif**, le taux de
  `lecture_sure` par tome, les traductions d'onomatopée refusées et les crops exportés. Un
  filtre muet est la façon dont on perd les zones suivantes sans le voir.
- Les six clés neuves sont déclarées dans **`core/config_schema.py`**, avec leur nature et la
  raison de chaque choix. ⚠ `aire_max_frac` et `remplissage_max` sont typées `fraction` et non
  `positif` : **0 désarme**, et c'est le défaut livré.
- **Le compte de tests passe de 2 852 à 2 909** (2 852 dans la boucle courte, 57 désélectionnés)
  — 57 tests neufs, dont un qui aurait échoué avant le lot pour chaque étape. Les quatre
  publications du chiffre sont resynchronisées, comme `tests/test_coherence_chiffres.py`
  l'exige.
- **Corrigé en passant : `sfx_refus` était une liste morte.** L'orchestrateur y accumulait
  depuis le lot 13 chaque glose non plaçable, et ne la passait **jamais** à
  `report_manga.write_report`, qui n'avait pas de paramètre pour la recevoir. Les refus
  étaient comptés, mis en forme, puis jetés. Le paramètre est ajouté, la section apparaît, et
  les refus de traduction brodée y vont par le même chemin.

### Ce que le lot ne fait pas

**Il ne dessine rien.** `clean.clean_bubbles` n'est pas touché, `tests/test_manga_clean.py`
n'est pas modifié d'une ligne et passe, le mode par défaut reste `"rapport"`. Le principe
directeur — « l'IA ne dessine jamais » — est intact ; `PLAN-22` est le seul lot autorisé à le
renégocier.

**Deux critères du plan sur onze ne sont pas tenus**, pour une cause unique : aucun serveur LLM
vision n'était joignable sur la machine de mesure, la voie A est donc implémentée mais **non
mesurée**, et le taux de `lecture_sure` vaut 0 % partout. C'est écrit, avec la commande qui le
lèvera. La voie B, elle, est tranchée : le recogniseur de *koharu* n'existe pas, et le seul
vrai candidat — `hayai-ocr-v2`, **Apache-2.0**, entraîné avec un jeu d'onomatopées — est
publié en `safetensors` seulement (623 Mo, `trust_remote_code`), ce qui imposerait `torch`.
**Ouverte en droit, fermée en pratique**, condition de réouverture nommée : un export ONNX.

La distribution qui décide de `PLAN-22` est publiée : sur 2 455 zones, **53,2 % ont un fond
local d'uniformité ≥ 0,60** (un remplissage déterministe suffirait), **36,2 % sont dans la
bande ambiguë** et **10,6 % sous 0,35** (le palier « ne rien peindre »). Aucun creux : c'est le
troisième cas prévu par le plan, et `PLAN-22` doit écrire **deux chemins**, pas un.

Les onze critères un par un, les quatre prémisses fausses, et **ce que la mesure ne dit pas** :
[`docs/mesures/sfx-2026-08-28.md`](docs/mesures/sfx-2026-08-28.md). La vérité terrain :
[`docs/mesures/sfx-echantillon-2026-08-28.json`](docs/mesures/sfx-echantillon-2026-08-28.json).

---

## [2.11.0] - 2026-08-28

### MINEUR — Lot 20 : l'atelier GitHub, ou la fin des vérifications qu'on oublie

Le dépôt vérifiait **dix-neuf choses à la main** avant chaque commit et chaque publication.
Aucune n'était écrite au même endroit, plusieurs n'étaient écrites nulle part, et deux d'entre
elles se sont avérées **non tenues depuis leur adoption** au moment où on les a branchées à un
outil. Ce lot les recense, en automatise quinze, et dit lesquelles restent humaines et
pourquoi.

**Aucun changement au pipeline.** Aucun prompt, aucun seuil, aucune étape, aucun format de
sortie, aucune clé de `config.yaml` — dont l'empreinte SHA-256 est inchangée. Aucun cache n'est
invalidé, `checkpoints.FORMAT_VERSION` est intact, les deux CLI ne sont pas touchées. Le MINEUR
tient à trois capacités neuves — une variable d'environnement, cinq garde-fous, un workflow de
publication — et à la règle du dépôt qui range « nouveau garde-fou » en MINEUR.

Le tableau des dix-neuf vérifications, les mesures, les dix critères un par un et **ce que la
mesure ne dit pas** : [`docs/mesures/atelier-github-2026-08-28.md`](docs/mesures/atelier-github-2026-08-28.md).

#### Le défaut principal, et il valait le lot à lui seul

`tests/conftest.py` fabriquait sa planche synthétique avec `C:/Windows/Fonts/msgothic.ttc` et
**skippait** la fixture quand le fichier manquait. Sur un runner Linux, `synthetic_manga_page`
aurait donc été sautée **en silence** — et avec elle toute la couverture détection / OCR /
orchestrateur de la brique manga. `pytest` sort 0 sur « tout sauté » : la CI aurait été verte
en ne testant plus rien de ce qui coûte cher. C'est ce silence, et non la police, qui clouait
la CI à `windows-latest` depuis le premier jour.

Trois changements, **dans cet ordre**, parce que l'ordre est le point :

1. `tools/polices.py` résout la police par `ANGELITH_POLICE_JP` puis par une liste de candidats
   par plateforme ;
2. `tests/test_fixture_police.py` **échoue** — il ne skippe pas — quand aucune police n'est
   trouvable, et son message nomme la commande d'installation. Ce test aurait dû exister depuis
   le début : il ne coûte rien sous Windows, et il aurait rendu le problème visible ;
3. **seulement alors**, la matrice `[windows-latest, ubuntu-latest]`, avec un job qui casse le
   build si les deux OS ne collectent pas le même nombre de tests.

#### Ajouté

- **`ANGELITH_POLICE_JP`** — la police japonaise des tests et du corpus synthétique devient
  configurable ([`tools/polices.py`](tools/polices.py)). Défaut iso-comportement sous Windows :
  `msgothic.ttc` reste le premier candidat. Trois candidats sous Windows, cinq sous Linux
  (`fonts-noto-cjk` en tête, celui de la CI), trois sous macOS — ces derniers pour un
  contributeur, **pas** pour la CI, `docs/roadmap.md` classant macOS hors périmètre.
  ⚠ Une valeur pointant sur un fichier absent est une **erreur**, pas un repli silencieux : le
  repli silencieux est exactement ce que ce lot supprime.
- **Une matrice d'OS** dans `ci.yml` — `windows-latest` **et** `ubuntu-latest` — et le job
  `collecte` qui compare les deux relevés et **échoue** s'ils diffèrent. Un test non collecté ne
  se voit nulle part dans un compte-rendu ; c'est la même logique que la mesure « collectés
  avec PySide6 contre sans » qui justifie son installation.
- **Cinq garde-fous, tous lançables en local** — un garde-fou qu'on ne peut vérifier qu'en
  poussant se découvre faux au moment où il refuse à tort une PR pressée :
  - [`tools/verifier_disclosure.py`](tools/verifier_disclosure.py) — la disclosure IA de
    `CONTRIBUTING.md`. ⚠ **Livré NON BLOQUANT**, taux mesuré **7 commits sur 105** (7 %) au
    2026-08-28, **bascule écrite au 2026-10-01**. `Assisté par : aucun` est accepté ;
    `Revu et testé manuellement : non` **passe le job et bloque la fusion**, par un second job
    distinct qui, lui, est bloquant dès maintenant.
  - [`tools/verifier_arbre.py`](tools/verifier_arbre.py) — ni poids de modèle, ni fichier sous
    `sources/`/`build/`, ni titre d'œuvre en clair. Bloquant sur les **lignes ajoutées** ;
    l'arbre entier est mesuré et publié sans bloquer.
  - [`tools/verifier_livraison.py`](tools/verifier_livraison.py) — CHANGELOG, version, nom du
    fichier de prompt, tableau daté. Échappatoire **nommée** : l'étiquette de PR
    `sans-changelog`, visible dans la liste des PR plutôt que cachée dans un message.
  - [`tools/compte_de_tests.py`](tools/compte_de_tests.py) — le compte collecté, et sa
    comparaison entre deux systèmes.
  - [`tools/notes_de_version.py`](tools/notes_de_version.py) — les notes de release découpées
    dans le CHANGELOG, avec vérification que le tag correspond à `core/version.py`.
- **`tests/test_coherence_chiffres.py`** — la règle de `docs/chiffres-de-reference.md`, vérifiée
  là où elle est décidable : le compte de tests identique **avec sa date** dans les trois
  fichiers qui le citent, l'arithmétique du tableau (2 795 + 57 = 2 852), la date/commit/
  empreinte de chaque `docs/banc-*.md`, et la concordance des licences de modèles entre les
  trois documents qui les déclarent.
  ⚠ Il ne vérifie **pas** que « tout chiffre porte son dénominateur » : ce n'est pas décidable
  par une expression régulière, et un garde-fou qui produit des faux positifs sur de la prose
  est contourné avant d'avoir servi.
- **`.github/workflows/garde-fous.yml`** — quatre jobs sur `pull_request`.
- **`.github/workflows/publication.yml`** — sur un tag `vX.Y.Z` : vérifier que le tag
  correspond à `core/version.py`, découper la section de CHANGELOG et en faire le corps de la
  release. Le CHANGELOG **est** déjà des notes de version ; en rédiger de secondes créerait un
  texte parallèle qui divergerait.
- **`.github/dependabot.yml`** — `pip` et `github-actions`, **mensuel et groupé**. ⚠ Pas
  hebdomadaire : sur un projet à un mainteneur, un flux continu de PR de dépendances devient du
  bruit qu'on cesse de lire, et c'est ainsi qu'une mise à jour cassante passe.
- **Le tableau du banc en résumé de job**, précédé de ce qu'il **ne** mesure **pas** (« corpus
  synthétique uniquement — le corpus réel se mesure en local par `python tools/banc.py --tous` »),
  conservé 90 jours en artefact, et un **run hebdomadaire** qui met à jour `onnxruntime` et
  `numpy` avant de mesurer.

#### Corrigé

- **Le skip silencieux de `synthetic_manga_page`** — cf. ci-dessus. C'était le défaut central.
- **La procédure de publication reposait sur trois `grep` recopiés à la main** d'une
  publication à l'autre, où un motif oublié dans la recopie ne se voit pas.
  `docs/PUBLICATION-ANGELITH.md` porte désormais un bloc `<!-- motifs-de-fuite -->` que
  `tools/verifier_arbre.py --index` lit — une commande, sur l'index, avant le commit. ⚠ Les
  motifs restent dans ce fichier et **nulle part ailleurs** : les recopier dans un outil publié
  publierait la liste des titres avec l'outil. Sur la branche `public`, où le fichier est
  retiré, le script **se déclare aveugle et sort en erreur** au lieu de rendre un vert.
- **Le compte de tests**, remesuré et daté : **2 852** collectés toutes dépendances
  optionnelles installées, **2 795** dans la boucle courte, **57** désélectionnés, au
  2026-08-28. Les trois fichiers qui le citent portaient 2 262 (2026-08-25).

#### ⚠ Ce que le lot a trouvé et n'a pas corrigé

**Dix-neuf fichiers suivis portent un titre d'œuvre en clair**, alors que
`docs/PUBLICATION-ANGELITH.md` demande depuis le 2026-08-21 une désignation neutre. La
vérification « doit ne RIEN renvoyer » de la procédure de publication **ne renvoie pas rien
aujourd'hui**, et n'aurait rien renvoyé aux publications passées. La purge du corpus a traité
l'**arborescence** — qui était le risque principal, et qui est bien purgée ; elle n'a pas
traité la **prose**. Le garde-fou tire d'ailleurs sur le commit précédent (`51ad6e1`), qui a
ajouté un titre dans un plan hier.

Leur nettoyage n'est pas dans ce lot et c'est délibéré : `CHANGELOG.md` et `config.yaml` sont
des documents historiques, et réécrire une entrée datée pour en retirer un mot est une
réécriture de l'histoire. La liste exacte est publiée, fichier par fichier, avec son décompte.

#### ⚠ Ce que la mesure ne dit pas

**Aucun workflow GitHub Actions n'a été exécuté.** Les cinq fichiers YAML sont validés et toute
la logique qu'ils appellent est testée hors CI (**71 tests neufs**), mais la matrice Linux, le
job de comparaison de collecte et le workflow de publication n'ont jamais tourné. Trois des dix
critères du plan sont donc « tenus au code, non vérifiés en exécution » — et ils sont nommés
comme tels dans le document du lot, pas présentés comme acquis.

## [2.10.0] - 2026-08-27

### MINEUR — Lot 19 : le système visuel, ou une interface qui a l'air d'un logiciel

Il n'y avait pas de système de design : il y avait **vingt-six couleurs littérales**, dix-neuf
valeurs distinctes, dans cinq fichiers, sans aucun point de définition commun. Zéro feuille de
style d'application, zéro `QPalette`, zéro `setStyle` — donc le style natif de la plateforme,
qui **ignore une grande partie du QSS**, ce qui explique que les **douze** `setStyleSheet` du
dépôt aient tous été inline sur un widget unique : c'était le seul endroit où ils prenaient.

Et un défaut qui se voyait à l'œil nu : les gris `#9aa`, `#7aa` et le `#d2d2d2` du journal sont
des valeurs de **thème sombre**, appliquées sur des widgets que Windows peint en **blanc**.
Onze paires texte/fond mesurées, **onze sous leur cible WCAG** — le niveau `info` du journal, le
plus fréquent, à **1,51:1**, c'est-à-dire illisible. L'application mélangeait deux hypothèses de
fond contradictoires, par accident.

**Aucun changement au pipeline.** Aucun prompt, aucun seuil, aucune étape, aucun format de
sortie, aucune clé de `config.yaml` — dont l'empreinte SHA-256 est inchangée
(`d971be6a…70566e5`). Aucun cache n'est invalidé, `checkpoints.FORMAT_VERSION` est intact, les
deux CLI ne sont pas touchées. Le **comportement** ne change pas ; l'apparence, si. D'où le
MINEUR.

Le tableau de contraste des deux thèmes, les captures avant/après, les neuf critères un par un
et **ce que la mesure ne dit pas** :
[`docs/mesures/systeme-visuel-2026-08-27.md`](docs/mesures/systeme-visuel-2026-08-27.md).

#### Ajouté

- **Un thème clair et un thème sombre**, avec bascule dans « Affichage → Thème » (*Suivre le
  système* · *Clair* · *Sombre*) et choix persisté dans `.angelith/interface.json`. Le défaut
  est **`auto`** : l'interface suit `QStyleHints.colorScheme()`, avec repli sur le clair — le
  seul défaut iso-perception, puisque l'application portait jusqu'ici le style natif.
  ⚠ **Le canevas reste sombre dans les deux thèmes.** Trois surfaces et non deux : `chrome`
  suit le thème, `canevas` non, `journal` est monospace et contrasté. Un fond sombre autour
  d'une planche est la convention de tous les outils d'image, et `QColor(40,40,44)` l'appliquait
  déjà — ce qui n'était pas acceptable était que le formulaire d'à côté soit clair par accident.
- **`gui/theme.py`, le seul endroit du dépôt où une couleur a le droit d'être écrite.** 32 rôles
  nommés **par usage et non par valeur** (`avertissement`, pas `orange`), deux palettes, une
  échelle d'espacement à six pas, une échelle typographique à quatre rangs, le calcul de
  contraste WCAG 2.1, et la feuille de style assemblée depuis les rôles.
  ⚠ **Aucun import Qt au niveau du module** : Qt n'apparaît que dans le corps de `appliquer()`,
  `qcolor()`, `qpalette()` et `police_mono()`. C'est ce qui permet à `gui/pellicule.py` —
  Qt-libre — de consommer les rôles sans casser la règle de couche, et au job de CI sans PySide6
  d'exécuter les garde-fous de contraste. Un test le vérifie **par lecture du source**.
- **Le tableau de contraste est publié et vérifié** : 35 paires × 2 thèmes = **70 mesures, zéro
  échec**, à 4,5:1 pour le texte courant et 3:1 pour les gros textes, bordures et états. Trois
  couleurs ont dû changer pour y arriver — la cible ne bouge pas, la couleur si.
- **Le style `Fusion`**, prérequis de tout le reste : il respecte à la fois `QPalette` et le QSS,
  ce que `windowsvista` ne fait pas. Repli `ANGELITH_STYLE_NATIF=1` le temps d'une mise au
  point — pas un réglage, il n'apparaît dans aucun menu.
- **Douze icônes SVG en ligne**, teintées par un rôle du thème (`currentColor` substitué au
  rendu), plus un `setWindowIcon` : l'application portait l'icône Qt par défaut dans la barre
  des tâches. **Pas de `.qrc`** — le projet n'est pas empaqueté et ne veut pas l'être ; une
  étape `pyside6-rcc` ajouterait un artefact généré à committer.
  ⚠ **Icône *et* libellé sur les cinq boutons de mode**, jamais l'icône seule : « Redessiner »
  remet l'OCR et la traduction de la bulle à zéro, et aucun pictogramme ne dira jamais cela.
- **Les cinq états visuels qui n'existaient pas** : `:disabled` (lisible, pas effacé — c'est
  l'état des huit widgets mutants pendant chaque run), lecture seule **≠** désactivé, `:checked`,
  `:focus` (anneau de 2 px, ≥ 5,95:1 dans les deux thèmes), `:hover` sur les vignettes.
- **L'alternative clavier aux gestes de canevas** : flèches pour déplacer la zone sélectionnée
  (1 px, 10 px avec `Maj`), `Ctrl`+flèches pour la retailler. Le dépôt est temporisé à 500 ms —
  `zone_retaillee` réécrit `regions.json`, `masks.png` et repeint la planche nettoyée, soit de
  l'ordre de la seconde ; une écriture par flèche rendrait le geste inutilisable.
  ⚠ **Dessiner une zone au clavier n'est PAS couvert**, et un test verrouille ce périmètre
  plutôt que de laisser croire le contraire.
- **30 widgets portent un nom accessible** (il y en avait zéro) — 26 sites d'appel, dont un
  dans la boucle des cinq outils. Tout widget dont le libellé visible n'est
  pas un mot — `🔒`, `−`, `+`, `%` — et sur les trois listes sans `QLabel` associé.
- **Un `setTabOrder` explicite par panneau** (il y en avait zéro).
- **Le troisième état vide** : une planche affichée sans aucune bulle. Bandeau au-dessus du
  canevas — pas une page à sa place, c'est la planche qu'on est venu regarder — avec le bouton
  « Tracer une bulle à la main ». Il distingue *jamais analysée* de *analysée, zéro bulle* : le
  premier est du travail à faire, le second un résultat, juste sur une illustration pleine page
  et faux sur une planche dialoguée.
- **`tools/captures_gui.py`** : quatorze captures de l'interface — les deux onglets et les cinq
  boîtes de dialogue, dans les deux thèmes — sur un tome **synthétique**, pour ne pas verser une
  planche sous droit d'auteur dans `docs/`. Ce sont elles qui ont trouvé la régression du thème
  non appliqué que soixante-dix mesures de contraste laissaient passer.
- **Les gestes clavier du canevas sont dans la boîte « Raccourcis clavier »**, avec leur
  périmètre : « tracer une zone reste un geste de souris ». Un geste qu'on ne sait pas possible
  n'existe pas.

#### Corrigé

- **Le bandeau manquant de « Comparer au rendu du pipeline ».** Cocher ce bouton coupe **toute**
  interaction du canevas — les poignées et les calques disparaissent — et le seul indice était
  l'état enfoncé d'un bouton, alors que le cas voisin du run affichait « — affichage seul »
  depuis toujours. Deux situations identiques pour l'utilisateur, un seul bandeau.
- **L'ordre de tabulation traversait les quatorze boutons de la barre du canevas.** L'ordre
  implicite allait recherche → remplacement → bouton → résultats → filtre → pellicule → *les
  quatorze boutons* → vue → liste de bulles → inspecteur : passer du champ de réplique au bouton
  « Retraduire » demandait une dizaine de tabulations, sur le geste le plus répété du logiciel.
  Il en demande **trois**, et un test verrouille la mesure. Les trois boutons de zoom sortent du
  parcours (`NoFocus`) : ils ont chacun un raccourci de menu.
- **L'aplat d'attente d'une vignette était invisible** : `#e9e9ec` sur le blanc d'une liste, soit
  **1,21:1**, alors que sa propre docstring affirmait qu'il donnait « cette lecture d'un coup
  d'œil ». C'est le seul changement de ce lot qui se voit vraiment à l'usage.
- **Un nom de classe Python était la seule chose que l'utilisateur voyait d'un échec.**
  `f"{type(err).__name__} : {err}"` allait dans le journal **et** dans la barre d'état.
  `PermissionError` est excellent dans un rapport de bug et inutilisable au moment où l'on
  cherche quoi faire. Le nom de classe reste au journal ; la ligne visible dit ce qui a échoué
  et ce qu'on peut tenter. ⚠ Un test existant encodait l'ancien contrat
  (`test_une_tache_qui_leve_ne_tue_pas_le_fil`) : il vérifie désormais les **deux** canaux
  plutôt que d'être relâché.
- **« Onglet Runs → Lancer » était une phrase, pas un geste.** L'état vide d'un tome jamais
  traité porte maintenant un bouton, qui ouvre l'onglet **et y reporte le tome choisi** — sans
  quoi le clic suivant aurait lancé un run sur autre chose.
- **Les fenêtres des tests n'étaient jamais détruites.** `deleteLater()` poste un
  `DeferredDelete` que seule une boucle d'événements consomme, et `tests/test_gui_fenetre.py`
  n'en fait tourner aucune : ses 48 fenêtres restaient vivantes jusqu'à la fin de la session Qt,
  soit **4 800 widgets**. Invisible jusqu'ici ; avec une feuille de style d'application, qui
  restyle tous les widgets vivants, une bascule de thème coûtait **85 s**. Le fichier passe de
  **313 s à 23,7 s**. La fuite préexistait ; c'est la mesure qui est neuve.
  ⚠ Le premier correctif de ce coût sautait l'application du thème sur l'égalité des **modes**,
  ce qui laissait une fenêtre neuve **sans une seule règle de style** — journal en Segoe UI,
  ligne d'état en noir. Les 70 mesures de contraste passaient quand même : elles interrogent la
  palette, pas le widget. C'est `theme.appliquer` qui compare désormais la **feuille produite**,
  et trois tests encadrent le cas, dont un qui interroge la police réelle du journal.

#### Changé

- **`px` → `pt` partout.** Cinq `font-size` en pixels et un `setPointSizeF(16)` absolu ne
  suivaient ni le réglage système ni le facteur DPI. L'échelle dérive maintenant de
  `QApplication.font()`, donc de l'utilisateur, et un test refuse qu'un `max()` mal placé écrase
  ses deux premiers rangs.
- **Une pile monospace multiplateforme** pour le journal et les panneaux de texte. `Consolas`
  reste en tête — c'est la police de la machine de développement — mais six replis **nommés** la
  suivent (`Cascadia Mono`, `SF Mono`, `Menlo`, `DejaVu Sans Mono`, `Liberation Mono`,
  `monospace`). `font-family: Consolas, monospace` était le genre de valeur qui rend un logiciel
  « développé sur Windows » visible au premier coup d'œil ailleurs.
- **`gui.pellicule.couleur()` devient `role_couleur()` et rend un RÔLE**, pas une valeur. Elle
  était le seul endroit du dépôt qui nommait l'idée d'un thème, en rendant `None` pour « couleur
  par défaut » ; il lui manquait un vocabulaire. Le module reste Qt-libre : il décide d'un état,
  jamais d'un pixel. *(API interne, aucun effet utilisateur.)*
- **Les sélecteurs de la feuille nomment leur classe, jamais `*[role=…]`.** Un sélecteur
  universel avec attribut force Qt à évaluer la propriété dynamique sur chaque widget, à chaque
  résolution de style. `poser_role()` refuse donc aussi les classes que la feuille ne nomme pas :
  une règle QSS qui ne s'applique pas est **silencieuse**.

#### Tests

**102 tests neufs**, dont **40 tournent sans PySide6**. Comptes mesurés le 2026-08-27 sur le même
poste, par `pytest --collect-only -q` : **2 655 → 2 757 avec PySide6**, **2 515 → 2 555 sans**.

Le garde-fou central est un test qui **parcourt les fichiers de `gui/`** et échoue sur tout
`#rrggbb` ou `QColor(…)` littéral hors de `theme.py`. Sans lui, les vingt-six couleurs
reviendraient une par une : le plan en annonçait vingt, le relevé en a trouvé vingt-six — six de
plus ajoutées par le seul lot 18 — et l'inventaire manuel du plan en avait **manqué trois**,
dont le numéro d'ordre de lecture, « l'information la plus utile de tout l'écran ».

#### Ce que ce lot ne fait pas

Aucune action nouvelle au-delà de la bascule de thème, aucune refonte de disposition, aucune
animation, aucun changement au pipeline. Les hauteurs maximales de quatre champs restent codées
en dur, dette assumée et écrite. **Aucun lecteur d'écran réel n'a été essayé** : le lot démontre
que l'information existe pour lui, pas qu'elle lui suffit. Et les captures ont exhumé un défaut
**antérieur** qui n'est pas corrigé ici : les boutons standard de Qt s'affichent en anglais
(« Close », « Cancel »), faute de `QTranslator` chargé — cela demande une infrastructure de
traduction, pas un token de couleur.

---

## [2.9.0] - 2026-08-27

### MINEUR — Lot 18 : l'interface cesse d'exiger la ligne de commande

Un utilisateur qui installait Angelith, lançait `python gui.py` et n'avait pas de dossier
`sources/` obtenait deux listes déroulantes vides, un éditeur vide, et **une phrase de journal**
qui décrivait un geste à faire ailleurs : créer une arborescence à la main dans l'explorateur de
fichiers. Il n'y avait ni écran d'accueil, ni sélecteur de fichier (**zéro** `QFileDialog` dans
tout `gui/`), ni glisser-déposer (**zéro** `setAcceptDrops`), ni mémoire d'une session à l'autre
(**zéro** état persisté), et **un seul menu à six entrées**.

Quatre actions du menu de la console `rich` (`app.py`) n'avaient **aucun** équivalent graphique :
importer un glossaire, l'optimiser, tester le LLM, lancer le diagnostic complet.

**Aucun changement au pipeline.** Aucun prompt, aucun seuil, aucune étape, aucun format de
sortie, aucune clé de `config.yaml` — dont l'empreinte SHA-256 est inchangée. Aucun cache n'est
invalidé. Les deux CLI ne sont pas touchées. D'où le MINEUR : de nouvelles capacités d'interface,
et rien qui casse.

Mesures, verdicts critère par critère et **ce que la mesure ne dit pas** :
[`docs/mesures/coquille-applicative-2026-08-27.md`](docs/mesures/coquille-applicative-2026-08-27.md).

#### Ajouté

- **Créer un projet depuis l'interface.** État vide à deux boutons dans le panneau « Planches »
  (et non plus un aplat gris), boîte « Nouveau projet » avec `QFileDialog`, pré-remplissage du
  nom depuis la source, poids annoncé avant la copie. Les fichiers sont **copiés** sous
  `sources/`, jamais référencés, et la copie passe par le fil de travail — une archive de
  plusieurs centaines de mégaoctets ne gèle pas la fenêtre. `manga/creation_projet.py`, en
  Python nu, testable sans Qt.
- **Glisser-déposer** sur la fenêtre : un dossier de planches, un `.cbz`/`.cbr` ou une image
  proposent la création d'un projet ; un `.yaml`, `.docx`, `.txt`, `.md` ou `.csv` propose
  l'import de glossaire. Retour visuel dans la barre d'état au survol, et **message explicite**
  sur un dépôt non reconnu ou mélangé — jamais un silence. Décision dans `gui/depot.py`, sans Qt.
- **Les quatre actions de la console arrivent dans l'interface** : import de glossaire
  (menu Projet et glisser-déposer), optimisation du glossaire (avec confirmation chiffrée sur le
  nombre d'entrées), test de la connexion LLM et diagnostic complet des deux briques
  (menu Aide, résultat dans un panneau sélectionnable). **Aucun code d'`app.py` n'est dupliqué** :
  les cinq passent par `core.glossary_import`, `pipeline.orchestrator.run_optimize`,
  `core.llm.test_connection`, `pipeline.doctor` et `run_manga._run_doctor`.
- **Cinq menus, 35 entrées, un sous-menu**, déclarés dans une table unique (`gui/actions.py`, sans
  Qt) : Fichier · Édition · Affichage · Projet · Aide. Toute action de l'interface est atteignable
  par un menu, et le menu affiche son raccourci.
- **Raccourcis ajoutés** : `Ctrl+Q` (quitter), `Ctrl+F` (chercher), `Ctrl+H` (remplacer), `F1`
  (raccourcis clavier), `Ctrl++` / `Ctrl+-` / `Ctrl+0` (zoom), `Ctrl+Tab` (onglet suivant),
  `1`–`5` (outils de dessin). Ces derniers sont mono-touche : ils passent par `keyPressEvent`,
  qui ne les voit que si aucun champ de saisie n'a consommé la touche — jamais par un raccourci
  de portée fenêtre, qui volerait le « 1 » tapé dans une réplique.
- **La disposition survit au redémarrage** : géométrie, colonnes, journal, filtre de pellicule,
  verrou de cadrage, onglet actif, dernier projet et dernier tome, cases du lanceur. Dans
  **`.angelith/interface.json`**, à la racine du dépôt — un JSON qu'on peut regarder, pas le
  registre Windows. « Affichage → Réinitialiser la disposition » l'efface.
  ⚠ **`--force` et `--dry-run` ne sont JAMAIS persistés** : une case cochée hier et retrouvée
  cochée aujourd'hui, c'est un tome relancé depuis la détection. Le filtre s'applique à
  l'écriture **et** à la lecture, le fichier étant éditable à la main.
- **Indicateur de travail non enregistré dans le panneau** : compteur à côté du bouton
  d'enregistrement, et pastille `●N` sur la vignette concernée dans la pellicule. Trois gestes
  (déplacer un bloc, changer le corps, retirer une correction) n'écrivaient jusqu'ici qu'une ligne
  dans un journal replié à zéro, qui ne se déplie tout seul que sur un avertissement.
- **Légende des symboles** (menu Aide) : le sens de `∅`, `⟳`, `✎N`, `↔N`, `⚠N`, `●`, `·` n'était
  accessible que par survol. La table est dérivée de celle qui dessine les pastilles — pas
  recopiée. Les **icônes** restent au `PLAN-19`.
- **Boîte « À propos »** : version, licence AGPL-3.0, et **provenance des poids de modèles** avec
  leurs licences amont, telles que `NOTICE` les décrit.
- **Préférences de l'interface** (menu Projet) : plafond du cache d'aperçus et fenêtre de
  préchargement, pour cette installation. `config.yaml` n'est toujours jamais réécrit.
- **Sauvegarde avant tout import de glossaire.** `core.glossary_import.import_into_project`
  réécrivait `sources/<Projet>/glossaire.yaml` — **partagé avec la brique light novel** — sans
  filet, alors que les deux autres chemins de réécriture en avaient un. Une sauvegarde
  `.avant-import.bak` part désormais avant, une seule fois, comme `.avant-multicibles.bak` et
  `.avant-reintegration.bak`. **Visible aussi depuis `app.py`** : un import par la console laisse
  maintenant ce fichier.

#### Corrigé

- **`Ctrl+Shift+S` était déclaré deux fois** dans la même fenêtre — sur le bouton et sur l'action
  de menu, tous deux enfants de la fenêtre. Une seule déclaration désormais, et un test qui
  parcourt la fenêtre entière (actions **et** boutons) refuse tout doublon.
- **La touche `Échap` était couplée à un libellé affiché** : `if bouton.text() == "Choisir"`.
  Renommer, traduire ou seulement compléter ce libellé cassait la touche, en silence. L'outil
  est maintenant retrouvé par son mode.
- **`F` (mono-touche) est passé à `Ctrl+0`, en gardant `F` comme alias.** Un raccourci
  mono-touche dans un panneau qui porte quatre champs de saisie n'était sauvé que par la
  neutralisation des gestionnaires de touches pendant une saisie — un filet, pas une conception.
- **Changer de tome jetait le travail non enregistré, sans un mot.** La fermeture protégeait par
  une boîte à trois choix ; le changement de tome vidait brouillons et documents
  inconditionnellement. **La même boîte** est maintenant appelée des deux côtés — une seule
  implémentation.
- **L'onglet « Runs » ciblait un tome qu'il n'avait pas choisi.** Sa cible était une étiquette en
  lecture seule remplie par l'onglet voisin, dont la liste est filtrée sur les tomes manga : **il
  n'existait aucun chemin d'interface pour lancer un run light novel sur un projet sans manga.**
  Le lanceur porte désormais ses propres listes projet/tome, remplies selon la brique choisie.
- **Une infobulle contredisait son code** : le champ de remplacement annonçait « Remplace dans la
  RÉPLIQUE affichée » alors que `_remplacer` applique sur toutes les planches cochées — et sa
  boîte de confirmation les nomme. L'infobulle est alignée sur le comportement.
- **Trois actions coûteuses partaient sans confirmation** : « Lancer » (un run de plusieurs
  heures), « Assembler » (réécrit CBZ et PDF) et « Appliquer ». Elles portent maintenant le
  récapitulatif chiffré qui existait déjà pour « Enregistrer tout le tome ».
- **Deux boutons dont le nom promettait la même écriture.** « Enregistrer **cette planche** » et
  « Enregistrer **tout le tome** (N planches) » — la portée est dans le libellé, le compteur
  aussi, et il est grisé à zéro.
- **`ci.yml` portait un couple de comptes de tests qui ne se reproduit pas** (2 007 / 1 879, soit
  128 tests d'interface). La même mesure au commit qui précède ce lot donne 2 516 / 2 415, soit
  **101**. Le commentaire est corrigé, daté, et dit sa méthode.

#### Changé

- **Le vocabulaire de la ligne de commande quitte les libellés, et reste dans les infobulles** :
  `--force (ignorer tout le cache)` → « Tout refaire depuis zéro » · `--dry-run` → « Simuler sans
  traduire » · `--verbose` → « Journal détaillé » · « Ouvrir config.yaml dans l'éditeur système »
  → « Réglages avancés (fichier) ». L'équivalent en ligne de commande est utile — pour qui
  scripte — mais il ne doit pas être le **nom** de l'action.
  ⚠ Les **étapes de reprise** (`rendu`, `traduction`, `terminologie`, `ocr`, `sfx`, `nettoyage`,
  `detection`) gardent leur identifiant : ce sont des noms de `checkpoints.STAGES`, ils
  apparaissent dans `RAPPORT.md` et dans la documentation.

#### Tests

**128 tests neufs**, dont **89 tournent sans PySide6** (`gui/actions.py`, `gui/reglages.py`,
`gui/depot.py`, `manga/creation_projet.py` sont en Python nu). Comptes datés du 2026-08-27, dans
la configuration de la CI : **2 644 collectés avec PySide6, 2 504 sans**, soit **140 tests
d'interface** — contre 2 516 / 2 415 et 101 au commit précédent. Sur ce poste, toutes dépendances
optionnelles installées : **2 679**.

#### Ce que ce lot ne fait pas

Aucun changement de couleur, de police, d'icône ni de thème (`PLAN-19`). Aucun empaquetage, aucun
installeur, aucune documentation anglaise. **Le troisième cas du glisser-déposer du plan** — une
image lâchée sur une vignette doit ne rien faire *et le dire* — n'est pas implémenté tel que
spécifié : une image seule est traitée comme une source où qu'elle tombe. L'écart et son
raisonnement sont dans le document du lot, §3.2.

---

## [2.8.0] - 2026-08-26

### MINEUR — Lot 16, étape zéro : les deux poids Apache-2.0 sont mesurés, et ils ne détectent pas des bulles

Le lot 16 devait affiner le détecteur de bulles. Son plan imposait une étape zéro : **mesurer
d'abord les deux poids publics Apache-2.0 entraînés sur du webtoon**, parce qu'il serait absurde
de dépenser trois semaines et du GPU avant de savoir ce qu'ils donnent. C'est fait, et le
résultat est publié — y compris la partie qui contredit le plan.

**Aucun comportement livré ne change.** Aucun poids n'entre dans le dépôt, aucune URL n'entre
dans `manga/models.py`, aucune clé de `config.yaml` ne bouge, aucun cache n'est invalidé. Ce lot
livre **un instrument de mesure et deux documents**. D'où le MINEUR — nouvel outil, rien ne
casse.

#### Le résultat

Sur les 9 bandes du webtoon de référence, le taux de bulles sans texte OCR : **13,2 %** pour le
détecteur en place, **13,8 %** pour `ogkalu/comic-speech-bubble-detector-yolov8m`, **11,1 %**
pour `ogkalu/comic-text-and-bubble-detector`. Le critère de sortie du plan — « le second avis
ramène l'essentiel des planches à zéro bulle **et** fait tomber le taux de faux positifs
webtoon » — **n'est pas rempli**.

Sur les **188 planches à zéro bulle** des dix volumes, le premier candidat en récupère **52** à
640 et **76** à 1 024. Puis on regarde les planches : sur un échantillon de **12 planches et
33 régions**, examinées une par une, **zéro ballon**. 22 régions sur 33 sont du texte de récit
**hors bulle**, 6 du texte éditorial, 5 de fausses détections franches (3 filigranes de scan,
2 morceaux de dessin). Ses poids le disaient — ses classes s'appellent `text_bubble` et
`text_free` — la fiche de son modèle non.

#### Ajouté

- **`tools/banc_candidats.py`** — le banc des détecteurs candidats. Trois familles d'export ONNX
  (`yoloseg`, `yolo`, `rtdetr`), le fenêtrage et le post-traitement **du pipeline** appliqués à
  tous les bras, l'arbitre (`detection_retry.arbitrer`) et le nettoyeur (`clean.analyze_bubble`)
  comme juges, l'OCR du projet en option (`--ocr`) et le détecteur de texte en option
  (`--texte`). Il n'écrit **rien** sous `build/`.
- **`manga/detection.assembler_fenetres`** — extrait de `BubbleDetector.regions_de_fenetres`,
  qui reste son seul appelant du pipeline. Refactor prouvablement neutre : il permet à un
  candidat qui ne rend que des boîtes de fenêtrer **exactement** comme le pipeline, sans
  réimplémenter la remontée en pleine page ni le dédoublonnage de coutures. Il prend un
  **itérable** et l'appelant du pipeline lui passe un générateur : matérialiser les huit
  fenêtres d'une bande de 10 000 px d'abord garderait vivants en même temps les masques de
  fenêtre et les masques pleine page, ce qui aurait été une régression mémoire sur le format
  qui en a le moins la marge.
- **`docs/mesures/detecteurs-candidats-2026-08-26.md`** — la mesure, ses dix sections, et ce qu'elle ne
  dit pas.
- **`docs/mesures/seuils-affinage-detecteur.md`** — **les quatre seuils de L9.3, écrits avant le premier
  entraînement**, qui n'a pas eu lieu. C'est le livrable qui rend un échec publiable.
- 13 tests neufs (`tests/test_banc_candidats.py`), sans modèle et sans réseau.

> **Le compte de tests, avec sa date et son dénominateur** (règle de
> `docs/chiffres-de-reference.md`) : **2 551 collectés** au 2026-08-26, toutes dépendances
> optionnelles installées — dont **2 491 exécutés** par la boucle courte
> (`-m "not modeles and not lent"`, 3 sautés, 57 désélectionnés) et **22** par la boucle
> `modeles`, qui passe elle aussi avec les poids en place. Les figures « 2 262 / 2 206 » qui
> circulent dans le dépôt sont datées du 2026-08-25 et ne sont pas réécrites ici : les
> réconcilier est l'objet du `PLAN-20`.

#### Corrigé (documentation)

- `manga_models/README.md` disait de `ogkalu/comic-speech-bubble-detector-yolov8m` : « bulles,
  boîtes », recopié de la fiche du modèle. Ses classes embarquées sont `text_bubble` /
  `text_free`, et la mesure le confirme. Le fichier porte maintenant le résultat, la façon de
  récupérer les poids (**le premier n'existe qu'en `.pt`** et demande un export `ultralytics`
  dans un environnement jetable), et les signatures ONNX vérifiées des deux.
- `docs/COMMANDES.fr.md` documente le nouvel outil, et **pourquoi `--ocr` ne dit rien sur un tome
  japonais** : `manga-ocr` est génératif, il rend rarement une chaîne vide.

#### Trois affirmations renversées par la mesure

- **« Un remplissage qui trouve une région uniforme a trouvé une bulle »** (plan du lot 16) :
  faux. Deux morceaux de skyline mesurent **0,807 et 0,818** d'uniformité — au-dessus même du
  seuil de nettoyage plein masque (0,60). Un ciel brumeux se remplit aussi uniformément qu'une
  bulle.
- **RT-DETR-v2 ne supporte pas `input_size: 1024`** : son rappel passe de **0,86 à 0,18** sur le
  corpus annoté. Il ne peut donc pas bénéficier du levier de résolution du lot 12, ni de
  l'escalade. Limite structurelle, pas réglage.
- **Relever `input_size` à 1024 fait BAISSER le rappel du détecteur en place** sur le corpus
  annoté (0,82 → 0,77), alors qu'il lui fait récupérer 19 planches muettes sur le corpus réel.
  Les deux sont vrais : la résolution aide les petites bulles et nuit aux grandes. Trois planches
  synthétiques ne tranchent pas — c'est écrit comme tel.

#### Décidé

Ne pas remplacer le détecteur, ne pas le brancher en second avis derrière l'escalade (ce qu'il
propose est du texte hors bulle, et le faire entrer par `kind="bulle"` le ferait relettrer comme
du dialogue), et **reporter `ogkalu/comic-speech-bubble-detector-yolov8m` au lot 21** — la
lecture du texte hors bulle — où il se mesurera contre `comic-text-detector`, qui est GPL-3.0 et
entraîné pour partie sur Manga109-s.

---

## [2.7.1] - 2026-08-26

### CORRECTIF — Lot Sonar : la couverture devient un chiffre vrai

SonarQube Cloud affichait **`Coverage: 0 %`** sur un dépôt qui collecte **2 455 tests** en
local et 2 007 en CI. Sonar ne se trompait pas : **aucun rapport de couverture n'était
produit** (pas de `pytest-cov`, aucune étape Sonar dans `ci.yml`), et l'analyse tournait donc
en *Automatic Analysis* — un mode qui ne **calcule** jamais la couverture Python, il ne sait
que lire un rapport qu'on lui fournit. Le zéro était une absence de mesure déguisée en mesure,
c'est-à-dire exactement ce que `ci.yml` passe trois pages de commentaires à refuser ailleurs.

Aucun changement de comportement, aucun fichier de sortie touché, aucune clé de configuration
du pipeline : d'où le CORRECTIF.

#### Ajouté

- **`.coveragerc`** — et pas `pyproject.toml`, que le dépôt refuse délibérément (`pytest.ini`
  ne sait pas lire de section coverage). `relative_files = True`, six paquets au périmètre,
  les cinq scripts racine dehors.
- **`sonar-project.properties`** — `projectKey` et `organization` reprises de
  `.sonarlint/connectedMode.json`, seule source de vérité du mode connecté de l'IDE.
  ⚠ `sonar.sources` est **énuméré** plutôt qu'écrit `.`, à cause d'une collision de nom à un
  caractère près : ce dépôt possède un dossier `sources/` qui contient les **œuvres à
  traduire** et n'a rien à voir avec `sonar.sources`. `CONTRIBUTING.md` porte la contrepartie
  — un futur paquet de premier niveau s'ajoute ici à la main.
- **`pytest-cov>=5.0`** dans `requirements-dev.txt`, et nulle part ailleurs : personne n'a
  besoin de mesurer une couverture pour traduire un tome.
- **Un job `sonar`** dans `.github/workflows/ci.yml`, `needs: [tests, banc]`, sur
  `ubuntu-latest` — ce n'est pas une entorse au contrat `windows-latest` de l'en-tête, qui
  porte sur les jobs qui *exécutent* des tests (la police `msgothic.ttc`). Action épinglée au
  correctif (`sonarqube-scan-action@v8.2.1`, vérifiée le 26/08/2026) parce qu'elle télécharge
  et exécute un binaire tiers, et que sa v8 a changé un défaut de vérification de signature.
- La commande locale équivalente dans `docs/COMMANDES.fr.md`, comme l'exige la première ligne
  de `ci.yml`.

#### Ce qui compte : DEUX rapports, pas un

Le job `tests` exclut délibérément les marqueurs `lent` et `modeles` — ils exigent les poids
ONNX que le dépôt ne commite pas. Si Sonar ne recevait que ce rapport, la couverture publiée
**exclurait toute la détection de bulles et l'OCR** — le code le plus cher et le plus risqué
du dépôt — tout en s'affichant comme « la » couverture du projet. C'est la CI verte qui ne
teste rien, transposée à un pourcentage. Le job `banc` produit donc son propre
`coverage-banc.xml`, et Sonar fusionne les deux via `sonar.python.coverage.reportPaths`.

Conséquence assumée de `needs: [tests, banc]` : si le banc échoue, **aucune** analyse n'est
publiée. Publier une couverture amputée en silence serait pire qu'une absence de publication.

#### Deux défauts trouvés PAR les contrôles du brief, et corrigés avant livraison

- **Le rapport n'appariait que 99 fichiers sur 115**, et personne ne l'aurait vu. Écrit
  `source = core, pipeline, manga, …`, `coverage.py` traite chaque paquet comme une racine et
  écrit des `filename` **sans préfixe** : `agents.py`, `checkpoints.py`, `orchestrator.py`. Or
  le dépôt porte **12 collisions de basename** entre ces paquets — `core/agents.py` et
  `pipeline/agents.py`, `manga/checkpoints.py` et `scan/checkpoints.py`, `__init__.py` six
  fois — qui s'écrasaient l'une l'autre, et Sonar n'avait aucun moyen de trancher entre six
  racines candidates. Une racine unique (la racine du dépôt) rend `manga/planche.py` et
  l'ambiguïté disparaît : **115 fichiers appariés**. Un appariement PARTIEL est pire qu'un
  zéro, parce qu'il a l'air plausible.
- **30 avertissements `Couldn't parse` par run.** PySide6 injecte dans l'interpréteur des
  modules dont le nom ressemble à un chemin relatif — `shibokensupport/signature/loader.py`,
  `signature_bootstrap.py`, `pyscript` — sans qu'aucun fichier existe sur le disque, et
  `relative_files = True` les prenait donc pour du code du projet. Ils n'atteignaient pas le
  XML et ne changeaient pas le pourcentage : c'était du bruit, et le bruit finit par cacher un
  vrai avertissement. Nommés dans `omit`.

#### Mesuré

Couverture locale : **80,6 %** sur 16 026 instructions et 115 fichiers, 2 455 tests.

| paquet | instructions | manquantes | couverture |
|---|---|---|---|
| `manga` | 6 312 | 575 | **90,9 %** |
| `pipeline` | 2 713 | 293 | 89,2 % |
| `scan` | 813 | 101 | 87,6 % |
| `core` | 2 153 | 363 | 83,1 % |
| `gui` | 2 830 | 1 161 | 59,0 % |
| `tools` | 1 205 | 618 | 48,7 % |
| **total** | **16 026** | **3 111** | **80,6 %** |

C'est le contrôle de plausibilité du brief : aucun paquet proche de zéro, donc aucun `source =`
mal ciblé. Les deux plus bas s'expliquent — des widgets Qt qu'on instancie sans les piloter, et
des outils en ligne de commande dont les `main()` ne sont pas joués.

- `coverage.xml` : chemins **relatifs**, séparateurs `/`, préfixés de leur paquet — vérifié
  attribut par attribut, aucun chemin absolu, aucun antislash **malgré une production sous
  Windows**.
- `--cov` ne change **pas** le nombre de tests collectés : 2 455 dans les deux cas.
- `ruff check .` passe.

#### Hors périmètre, et non fait

- Les issues et *security hotspots* remontés par Sonar.
- La ratification de l'« Intended architecture » : le graphe d'imports est propre et sans
  cycle, mais le figer transformerait chaque nouvel import légitime en « déviation » à
  arbitrer.
- Un quality gate personnalisé, des badges dans `README.md`.

#### ⚠ Deux actions MANUELLES restent à faire, sans quoi ce job échoue

1. **SonarQube Cloud** → `Administration > Analysis Method` → basculer sur *CI-based
   analysis*. Les deux modes sont **mutuellement exclusifs** : tant que l'automatique est
   actif, le scan lancé par la CI est **refusé**.
2. **GitHub** → `Settings > Secrets and variables > Actions` → créer `SONAR_TOKEN`, avec un
   jeton généré depuis `My Account > Security` sur SonarQube Cloud.

---

## [2.7.0] - 2026-08-26

### MINEUR — Lot 15 : le traducteur cesse de travailler à l'aveugle

Le pipeline ne fait pas un appel par bulle : l'unité est la planche entière, une liste
numérotée, un appel. C'est un bon choix, et le prompt système est soigné. **Le problème était
ce qu'il y avait dans le message.** Inventaire exact de ce que le modèle recevait pour traduire
une planche : le glossaire, les dernières répliques des trois planches précédentes, la place
disponible en pixels, la liste numérotée. Et c'est tout.

N'y figuraient ni **qui parle**, ni **la structure de la planche**, ni **le type de bulle** —
alors que le pipeline calcule déjà les trois, ou de quoi les calculer, et les jette :

- `ocr.reading_order` coupe la planche par ses gouttières et n'en gardait qu'un **ordre plat** ;
- `geometry.width_profile` calcule la plage contiguë **pour exclure la queue de la bulle**,
  c'est-à-dire le seul signal graphique qui désigne le locuteur — sa docstring le dit depuis
  toujours ;
- `BubbleRegion.kind` ne vaut que `"bulle"` ou `"onomatopee"`, et vaut `"bulle"` **1 599 fois**
  sur les deux tomes de référence, sans une exception.

**La règle qui gouverne tout ce lot : ne rien affirmer qu'on ne sache.** Un groupe faux fait
continuer une phrase par-dessus un changement de plan ; un type faux fait écrire un cri comme
un récitatif ; une étiquette de locuteur fausse fait tutoyer un inconnu. Dans les trois cas
**l'annotation absente vaut mieux que l'annotation fausse** — le modèle sait travailler sans,
c'est ce qu'il faisait avant. D'où le chiffre du lot : sur les **7 862 bulles** des dix volumes
de `build/`, **86,2 % restent « indéterminées »** — et c'est la propriété qu'il faut
surveiller, pas les quatre autres. Les seuils ont été calibrés sur un sous-ensemble de
2 534 bulles ; les 5 328 autres n'ont pas servi au réglage.

⚠ **Les prompts sont réécrits** : [`langues/fr/prompts/manga_traducteur.md`](langues/fr/prompts/manga_traducteur.md)
et [`langues/en/prompts/manga_traducteur.md`](langues/en/prompts/manga_traducteur.md), et deux
nouveaux — [`langues/fr/prompts/manga_relecteur.md`](langues/fr/prompts/manga_relecteur.md) et
[`langues/en/prompts/manga_relecteur.md`](langues/en/prompts/manga_relecteur.md).
`git checkout v2.6.0 -- langues/` reproduit la voix des tomes traduits avant cette version.

⚠ **Aucun cache n'est invalidé.** `structure.json` est un fichier ADDITIONNEL du cache de
planche : il n'entre ni dans `STAGES` ni dans `FORMAT_VERSION`, un cache antérieur ne le porte
pas, et le traducteur reçoit alors exactement l'énoncé qu'il recevait avant. Le mode `"texte"`
**sans les nouvelles clés** produit un résultat inchangé, vérifiable par diff de
`traduction.json` sur un tome.

#### Ajouté

- **`manga/consignes.py` — les seize instructions en dur du chemin manga, externalisées**, et
  **avant** d'enrichir le prompt, pas après. `docs/mesures/inventaire-couplage-fr.md` §5.2 les avait
  relevées : six f-strings et quatre chaînes fixes dans `orchestrator_manga.py`, deux dans
  `traduction_unitaire.py`, dont **une seule** était surchargeable par un pack de langue. Le
  lot en ajoute onze ; les écrire en dur aurait porté l'inventaire de 16 sites à 27 et refait
  dans deux versions le travail que la 1.9.0 avait déjà fait une fois. Le texte français reste
  à son site d'appel — `langues/fr/pack.yaml` déclare toujours `consignes: {}` —, le socle
  n'en connaît que les noms, et le pack `en` les déclare tous. Un gabarit au champ inconnu
  fait **refuser le pack au démarrage**, jamais au milieu d'un run de six heures.
- **`manga/planche.py` — la structure de la planche**, et `manga.structure` pour la régler.
  Groupes de mise en page, type de bulle, étiquette de locuteur. Tout est **déterministe et
  sans le moindre appel LLM** : morphologie de masque, gouttières, direction de queue.
  Mis en cache dans `.checkpoints/page_XXXX/structure.json`, ~14 ms par bulle.
  - **Les groupes** — `ocr.ordre_et_ruptures` rend en plus la **gouttière qui sépare chaque
    paire voisine**, ce qui permet de décider des groupes *après* la coupe plutôt que dans la
    récursion, où la géométrie seule ne sait pas répondre. ⚠ Le mot « case » n'apparaît nulle
    part dans le prompt : la coupe X-Y ne détecte aucune case, elle coupe des gouttières.
  - **La queue de bulle** — `geometry.profil_de_forme` l'extrait au lieu de la supprimer, et
    en tire une direction, donc un **locuteur probable**. Trois refus la rendent défendable :
    aucune saillie assez grosse, une saillie qui ne dépasse pas, deux saillies rivales — dans
    ce dernier cas on ne tranche pas, parce qu'une direction fausse est pire qu'aucune.
  - **Les types** — `dialogue` 6,9 %, `récitatif` 5,4 %, `pensée` 0,9 %, `cri` 0,6 %,
    `indéterminé` **86,2 %**. `tools/mesurer_structure.py` republie la distribution sur
    n'importe quel volume, **sans charger le moindre modèle**. ⚠ Le taux de dialogue varie de
    2,4 % à 20,1 % selon le tome, et ce n'est pas une variation de style : la queue n'est
    lisible que si le masque de détection la porte. Cette colonne mesure donc autant la
    qualité de segmentation d'un tome que sa proportion de répliques parlées.
  - **Les locuteurs** — étiquettes `[A]`, `[B]`, **locales à la planche** et annoncées comme
    seulement probables. Aucune reconnaissance de personnages : les seuls modèles publiés
    (*The Manga Whisperer*, CVPR 2024) sont sous licence de recherche académique, donc
    inutilisables dans un projet redistribué sous AGPL. La voie géométrique est la seule
    ouverte, et c'est un argument, pas un obstacle.
- **`manga.mode_traduction: "cible"`** — le premier passage est textuel, et **le diagnostic
  décide** d'une seconde tentative avec image. `"vision"` envoyait une image PLEINE PAGE pour
  **toutes** les planches du tome, sans condition, alors que son commentaire disait « à
  réserver aux passages ambigus » : le coût maximal pour les 90 % de planches qui n'en ont pas
  besoin, donc en pratique un mode que personne n'activait. En `"cible"`, ce sont les **crops
  des groupes** qui partent, pas la planche — cinq à dix fois plus légers et bien plus lisibles,
  parce que le sujet occupe le cadre.
- **`manga.onomatopees.vision`** — le crop de la zone est enfin joint à l'appel. C'était le cas
  le plus absurde du chemin manga : **une onomatopée est un dessin**, et la passe la traduisait
  depuis une lecture OCR dont `config.yaml` mesure lui-même qu'elle hallucine. Crop
  **rectangulaire brut**, pas l'encre isolée — c'est une mesure, pas un goût.
  ⚠ Défaut du code `false` (il faut un modèle capable de vision) ; la config livrée le
  recommande. ⚠ N'en déduis pas que `mode: "rapport"` peut changer : la lecture est un
  problème, le dessin en est un autre, et **l'IA ne dessine jamais**.
- **`quality_manga.bulle_trop_courte`** — le septième motif, symétrique de `bulle_trop_longue`.
  Les six autres sont morphologiques ou statistiques et **aucun** ne détectait une réplique
  abrégée : une bulle japonaise de 40 caractères rendue par « Ouais. » les passait tous. Or la
  pression est structurellement dans le sens de l'abrègement — on injectait un budget de
  caractères par bulle **sans aucune contrepartie sur la fidélité**. Seuil **calibré par
  famille de langue source** sur les paires source/rendu déjà en cache (1 702 bulles CJK,
  16 latines) : médiane 0,65 contre 1,06, d'où deux planchers et pas un.
- **`manga.garde_fous.ratio_court`** — et **chez le manga**. La clé `garde_fous` du light novel
  est de premier niveau, donc hors du bloc `manga:`, donc **structurellement inatteignable**
  depuis `config["manga"]` : c'est littéralement pourquoi `grep -rn perte_mots manga/` renvoyait
  zéro.
- **`manga/registre.py`** — vérifie **a posteriori**, et sans un seul appel LLM, que la
  traduction a suivi le registre que la fiche de contexte annonçait. Rien ne le faisait ; rien
  ne pouvait le faire. Même patron que les dérives d'orthographe T1/T2/T3 : purement lexical,
  donc actif même quand `manga_contexte` ne l'est pas, donc mesurable sur les tomes déjà
  produits. ⚠ Il **compte et signale, il ne corrige jamais** : un basculement de registre peut
  être une scène.
- **`manga/relecture.py`** — une passe de relecture **à mandat étroit**, et **désactivée par
  défaut**, comme le `correcteur` du light novel qui est à `null`. Quatre règles nommées
  (`registre`, `accord`, `contradiction`, `glossaire`) ; une correction qui ne nomme pas une
  règle connue est **rejetée par le code**, pas par le modèle. Cinq refus mécaniques : hors
  format, règle inconnue, bulle hors bornes, correction identique, correction vide.
  ⚠ La quatrième règle tourne **sans le modèle** : `termes_manques` est purement lexicale, et
  c'est elle qui alimente la colonne que `tools/banc.py` attendait explicitement.
- **`tools/mesurer_structure.py`** — la distribution du classifieur, et ses profils bruts.
  `tools/banc.py --traduction` gagne cinq colonnes : `glossaire manqué`, `registre`,
  `basculements`, `types de bulle`, `indéterminés`. Deux des trois lignes que son propre
  commentaire annonçait comme « lot 15 » sont donc livrées ; **aucun appel LLM**.
- `RAPPORT.md` : trois lignes neuves — structure de planche, registre de 2ᵉ personne, relecture
  — plus les lots coupés et la vision ciblée.

#### Corrigé

- **L'appariement image ↔ planche du mode lot.** La ligne était
  `[p.image_b64 for p in utiles if p.image_b64]` : le filtre **retire des éléments de la
  liste**, si bien qu'une seule planche à `image_b64` nul décalait toutes les suivantes —
  l'image *k* ne correspondait plus à la planche *k*, et rien dans le texte ne les reliait de
  toute façon. En vision le lot est écrêté à quatre planches : le désalignement portait sur au
  plus quatre planches, ce qui suffit à mettre les répliques dans les mauvaises bulles. Chaque
  image est désormais **nommée** dans l'énoncé. Correctif indépendant du reste du lot.
- **Le contexte inter-planches ne jette plus des planches entières.** `[-18:]` sur une liste
  chronologique garde la **fin** : sur une planche bavarde, la fin de N−1 et **rien** de N−3 ni
  de N−2. Silencieusement. Le budget est maintenant réparti entre les planches, et chaque ligne
  dit d'où elle vient — une liste plate redevient une séquence.
- **Le retry en température existe enfin en mode LOT.** `_translate_lot` faisait un unique
  appel puis tombait sur le repli, qui **rejoue la numérotation**, c'est-à-dire exactement ce
  qui vient d'échouer — et `config.yaml` mesure que c'est ce qui échoue à nouveau. Une seconde
  tentative coûte **un** appel de lot, contre vingt appels de planche pour le repli.
  ⚠ Une seule, quoi que dise `llm.max_retries` : sur un lot, une relance coûte la génération de
  cent trente répliques et le budget de raisonnement avec.
  ⚠ Et elle ne se déclenche pas pour une bulle vide **à raison** : un OCR qui vaut `（）` n'a
  rien à traduire, et c'est déjà le critère du repli par planche.
- **Le garde-fou de prefill n'avertit plus, il agit.** Ollama ne dégrade pas : il **jette
  silencieusement plus de la moitié du prompt**. « Avertir et continuer » revenait donc à
  produire des planches vides après un `warn` que personne ne lit avant le rapport. Le lot est
  désormais **coupé en deux** et chaque moitié refaite — pas un échec dur, ce qui trahirait
  l'intention d'origine.
- **La consigne de place est rééquilibrée.** « Dépasser force une police illisible » ne disait
  que la moitié qui pousse à couper. Le prompt dit maintenant que la place est une
  **contrainte de mise en page, pas un objectif**, et qu'abréger le sens est pire que
  déborder — le lettrage sait signaler un débordement (`typeset.debordement: "signaler"`), il
  ne sait pas deviner ce qui a été coupé.
- `checkpoints.invalider_textes` efface aussi `structure.json` : il est aligné par position sur
  `regions.json`, et une scission le décalerait d'un rang sans que rien ne le montre.

#### Mesuré et REFUSÉ

- **Le tri du cri par l'amplitude du relief.** Premier classifieur écrit, puis retiré : le
  94ᵉ centile du relief est atteint par les masques les plus **bruités** du tome, pas par les
  ballons en étoile. Un seuil posé là aurait typé « cri » les bulles les moins bien segmentées
  — exactement l'annotation fausse que ce lot s'interdit. Remplacé par une analyse
  **harmonique** : ce qui distingue une étoile d'un contour sale n'est pas l'amplitude, c'est
  la périodicité.
- **Un type `pensée` confortable.** Toute bande d'ondulation « moyenne » attrape 15 à 30 % des
  bulles, c'est-à-dire les bulles ordinaires. La conjonction retenue n'en garde que **0,9 %**,
  et c'est assumé : un vrai ballon de pensée mal typé reste traité comme un dialogue — le
  comportement d'avant ce lot — alors qu'un dialogue annoncé « pensée » ferait écrire une
  réplique en voix intérieure, sans rattrapage possible en aval.
- **Le veto du repli diagonal sur le groupement.** Là où `_coupe_ruptures` tombe sur son repli,
  il ne mesure aucune gouttière, donc ne déclare aucune rupture, donc **fusionne** — jamais il
  n'invente une coupure. Le drapeau est publié (≈ 37 % des planches) plutôt que transformé en
  veto sur une information saine.

#### Ce que ce lot ne fait PAS

- Aucune reconnaissance de personnages, donc **aucun suivi de locuteur entre planches**.
- Aucune mémoire entre chapitres ni entre tomes : la fiche de registre reste par tome, le
  glossaire reste le seul objet partagé.
- Aucun relettrage d'onomatopée.
- **Il ne gagne aucune bulle** : ce n'est pas son objet.
- Le relecteur est livré, instrumenté et **non recommandé** : il n'est pas encore mesuré sur du
  jugement humain. S'il ne gagne rien, il restera commenté — c'est un résultat aussi.

---

## [2.6.0] - 2026-08-26

### MINEUR — Le webtoon : cinq affirmations fausses, et la mémoire qu'on ne mesurait pas

Le format tourne de bout en bout depuis la 1.8.0. Le problème n'a jamais été qu'il ne marche
pas — c'est qu'**il produit un résultat faux**, et que personne ne savait à quel point. Ce lot
mesure d'abord, corrige ensuite, et **refuse** deux des réglages qu'il avait écrits, mesure à
l'appui. Tout est dans [`docs/mesures/webtoon-2026-08-26.md`](docs/mesures/webtoon-2026-08-26.md).

**Cinq affirmations que le dépôt et son plan portaient sont fausses**, dont deux écrites noir
sur blanc dans `config.yaml` : le fenêtrage coûte **7,1 s et non ~70 s** par bande ; **aucune**
des 71 fenêtres du corpus ne tombe sous le seuil d'encre (donc « de larges plages sans texte »
est faux ici) ; la détection de texte n'est **pas** inopérante sur bande — elle marque 6,65 %
de la planche ; le plafond de 255 régions n'est **jamais** approché (maximum mesuré sur
1 513 planches : **17**) ; et les « ~865 Mo de masques vivants » sont en réalité **270 Mo**.

**Le chiffre du lot.** Sur les 9 bandes de 1080×10 000 du chapitre de référence, le taux de
fausses détections — une région repeinte puis recollée faute de tout texte — passe de
**22,0 % à 15,1–17,0 %**, *sans perdre une seule vraie bulle*. Les 7 régions disparues sont
nommées une par une dans le document : 5 muettes, 1 doublon dont le texte passe sur la
survivante, 1 région dégénérée que `RAPPORT.md` signalait déjà. Le gain vient du dédoublonnage
de coutures par containment livré au lot 12 (L4.5), qui écarte **10 détections** sur ces
9 bandes.

⚠ **Le critère visé — moins de 5 % — n'est PAS atteint**, et le document le dit en tête.

**Ce qui reste est bien un défaut de DÉTECTION, et c'est mesuré**, pas supposé. Le plan
craignait l'inverse : ce chapitre étant le seul webtoon **et** le seul volume à source latine du
dépôt, ces bulles pouvaient n'être que des bulles dont `ocr_latin.py` n'a rien tiré. Le second
modèle — le détecteur de texte, étranger au chemin d'OCR — a été interrogé sur un **crop** de
chaque bulle, à ~20× la résolution qu'elle a dans la bande : les muettes couvrent **0,00 %,
0,00 % et 0,41 %** de leur masque en texte, les témoins lus **3,70 % et 4,08 %**. Deux
populations séparées d'un ordre de grandeur, sans recouvrement. ⚠ Échantillon petit et assumé
comme tel — 3 contre 2, la mesure ayant été arrêtée dès la séparation acquise ; elle oriente,
elle ne démontre pas. La suite est donc le **lot 16** (un détecteur entraîné sur du webtoon), et
non un correctif d'OCR.

#### Ajouté

- **La mémoire résidente, mesurée** — le seul chiffre que le dépôt ne produisait pas, et le
  seul qui dise si un tome tient sur la machine d'un contributeur. `core/memoire.py`, **sans
  aucune dépendance nouvelle** (`kernel32` par `ctypes` sous Windows, `/proc/self/status` sous
  Linux, `getrusage` ailleurs). `perf.log` porte le pic **en différentiel** autour de la
  détection et de la passe hors bulle ; `RAPPORT.md` porte le pic du run entier.
  Mesuré sur une bande : **637 Mo** pour la détection seule, **1,36 à 1,73 Go** avec la passe
  hors bulle — dont **+685 Mo pour une seule inférence** du détecteur de texte.
- **Un garde-fou contre le débordement silencieux du format d'étiquettes**, sur les **trois**
  chemins d'écriture — pipeline, SFX (qui a son propre compteur), édition manuelle. Au-delà de
  255 régions, `masks.png` s'écrit désormais en `uint16` au lieu d'enrouler ; au-delà de
  65 535, une erreur nomme la planche et le nombre.
- **`manga.detection.fenetre_occupation_min`** — le découpage des bandes se décide sur ce que
  le réseau VOIT de la planche (`petit_côté × input_size / grand_côté`, en pixels du canevas)
  et non plus sur une falaise de ratio.
- **`manga.detection.fenetre_encre_min`** — porte d'encre sur les fenêtres de détection, avec
  son compteur au rapport. Livrée **désarmée**.
- **`manga.onomatopees.fenetrage`**, `fenetre_hauteur`, `fenetre_recouvrement` — la passe hors
  bulle lit désormais une bande **fenêtre par fenêtre**, avec ses propres réglages (3 072 px de
  fenêtre, 1 600 px de recouvrement : ce modèle tourne à 1024 quand celui des bulles tourne à
  640, et le recouvrement doit couvrir le TEXTE — la colonne de katakana mesurée fait 1 470 px,
  la plus haute bulle 833). Sur une planche paginée, ce réglage ne fait **rigoureusement
  rien**.
- **`manga.formats.webtoon.rendu.psd_original: false`** — un chapitre de 9 bandes pèse
  **420 Mo** de PSD ; le calque du scan d'origine en est un tiers, et le scan reste sous
  `sources/`.
- **`RAPPORT.md`** : deux sections neuves — « PSD REFUSÉ » et « Fenêtres SAUTÉES sans
  inférence » — et une ligne de mémoire au résumé.
- `tools/apercu_detection.py` affiche, à chaque résolution essayée, **l'occupation du canevas**
  et le découpage qui en découle. Sans elle, un utilisateur qui obtient zéro bulle sur une
  bande ne peut pas savoir si le problème est un seuil ou une résolution effective de 69 px
  sur 640.

#### Corrigé

- **Le PSD d'une planche trop grande n'est plus écrit corrompu.** Le format plafonne à
  30 000 px de côté ; au-delà, `manga/psd.py` refuse **avant la première allocation**, la
  planche garde tous ses autres formats de sortie, et le rapport dit laquelle et pourquoi.
  ⚠ Le résultat le plus utile de cette étape est un non-événement : les 9 bandes de 1080×10 000
  produisent 9 PSD de 42,4 à 59,6 Mo **sans un seul échec**. La crainte n'était pas fondée à
  cette taille.
- Le seuil de découpage **suit désormais `input_size`**. À 1024, une planche au ratio 3,0 est
  vue 1,6× plus grande par le réseau et n'a plus besoin d'être découpée ; la falaise de ratio
  la découpait quand même, parce qu'elle ignorait la résolution. ⚠ Cela ne dispense pas une
  vraie bande de son fenêtrage : 1080×10 000 occupe encore 111 px du canevas à 1024. Relever
  la résolution complète le fenêtrage, elle ne le remplace pas.
- `config.yaml` documentait le fenêtrage à « ~70 s au lieu de ~8 s par planche ». **Mesuré :
  7,1 s contre 0,85 s.** Le facteur ×8,3 était juste, les valeurs absolues étaient dix fois
  trop grandes — et c'est sur ce « 70 s » que reposait l'intérêt de sauter les fenêtres vides.

#### Mesuré et REFUSÉ

Deux réglages que le plan demandait, écartés **par la mesure** et non par l'argument. Chacun
est livré, instrumenté et testé — mais **désarmé**, dans la lignée d'`aire_min_frac`.

- **La porte d'encre sur les fenêtres.** Sur les 71 fenêtres des 9 bandes, **aucune** ne tombe
  sous le seuil d'encre : la moins encrée est à 0,0065, la médiane à 0,79. C'est une bande
  couleur, illustrée d'un bord à l'autre. Ce qu'une porte parfaite économiserait se compte en
  secondes sur un tome de 48 minutes, contre le risque de sauter une fenêtre qui portait une
  bulle — le défaut même que le lot 12 vient de corriger.
- **La migration de `masks.png` en `uint16`.** Le maximum mesuré sur les 1 513 planches des dix
  volumes est de **17 régions** — et de **16 sur une bande de 10 000 px**. Réécrire 1 513
  fichiers de cache, en risquant d'invalider des heures de GPU, pour une marge dont quinze
  seizièmes ne servent à personne : le rapport n'y est pas. D'où le choix de largeur **par
  planche**, qui laisse tout le corpus existant intact au bit près.

#### Une décision renversée par la mesure suivante

Le fenêtrage de la passe hors bulle a d'abord été livré **désarmé**, et la ligne de changelog
était écrite. Rejeu sur la planche 3 (13 bulles, dialogue) : masque plus propre, **0 zone des
deux côtés**, six fois le prix — aucun gain.

Rejeu sur la planche **6** (1 bulle sur 10 000 px, page d'action) : **0 zone en pleine bande,
5 en fenêtré**, d'aires 1 227 à **39 607 px²** — c'est-à-dire des tailles d'onomatopée. C'est
exactement la planche pour laquelle cette passe existe, et la passe pleine bande y est
**aveugle**. Le défaut est donc `true`.

⚠ **Et la nuance, dite franchement** : sur la planche 1, un liminaire illustré, les deux passes
se trompent. La fenêtrée découpe le plus gros blob (480 001 → 285 444 px²) mais en rend deux
fois plus (4 → 8), et 285 444 px² font encore 2,6 % de la bande — du dessin pris pour du texte.
Cette planche nomme le prochain levier, que ce lot **ne tire pas** : il n'existe aucune borne
SUPÉRIEURE d'aire dans `hors_des_bulles`. Une borne se mesure, elle ne s'improvise pas à la fin
d'un lot.

⚠ Deux enseignements, et le second vaut mieux que le premier : une bande de dialogue et une
bande d'action ne mesurent pas la même chose, et **une seule planche aurait suffi à livrer le
mauvais défaut**. Au passage, l'affirmation de l'ancien plan — « la détection de texte est
structurellement inopérante sur bande » — est fausse dans les deux sens : en pleine bande elle
marque 6,65 % de la planche et rend 24 composantes (elle ne trouve pas rien, elle trouve des
taches) ; fenêtrée, elle trouve du vrai texte.

⚠ Ces cinq zones sont **détectées, pas lues** : la passe reste en mode `rapport`, rien n'est
dessiné sur la planche, et `manga-ocr` reste un modèle de dialogue.

#### Pas fait, et pourquoi

- **Le masque local avec sa boîte.** L'argument était « ~865 Mo de masques vivants sur une
  bande ». Mesuré : le maximum de candidates simultanées est de **25** (planche 3), soit
  **270 Mo** — et le pic réel du run est ailleurs, dans **une seule inférence** du détecteur de
  texte qui pèse +685 Mo et que le refactor ne touche pas. Onze modules lisent `.mask` ; un
  refactor de cette surface pour 270 Mo d'un pic de 1,7 Go, contre un risque de régression
  silencieuse sur le cache de détection de tous les tomes existants, ne se justifie pas. Ce
  qui manque pour le décider n'est pas un argument de plus mais **une planche qui fasse
  effectivement déborder la mémoire** — et le lot livre justement de quoi la reconnaître.

#### Les huit critères du plan

Publiés un par un dans le document de mesure, verdict compris. **Trois tenus**
(mémoire < 2 Go ; zéro régression sur le paginé ; plafond de régions sur les trois chemins),
**deux tenus sans qu'il y ait rien à faire** (aucun cache à migrer ; le PSD d'une bande ne
casse pas), **un à moitié** (les lobes de scission creux passent de deux à **un**, et le
survivant a la cause structurelle que le lot nomme et décline), **deux non tenus** — les 5 %
de fausses détections, et le nombre de bulles par bande.

⚠ Sur ce dernier : le compte **baisse** (6,6 → 5,9), à l'inverse du critère, et c'est le bon
signe — les 7 régions perdues sont nommées une par une, et aucune ne portait de texte qui ne se
retrouve ailleurs. Les deux critères se contredisent d'ailleurs partiellement : sur ce corpus,
avec ce détecteur, gagner des bulles c'est en gagner de fausses. Le lot a choisi le premier.

#### Compatibilité

**Aucun cache n'est invalidé, et c'est prouvé plutôt qu'affirmé.** Le `manga/detection.py`
d'avant le lot a été rechargé depuis `git show HEAD:` sous un autre nom, et les deux versions
ont tourné sur les mêmes planches avec le même modèle : **60 planches paginées** de *manga A*
Vol.1 et Vol.2, boîtes **et masques** comparés élément par élément, **0 écart**. Et sur la
seule décision que le lot change dans ce chemin — faut-il découper ? — le rejeu porte sur **les
1 513 planches** des dix volumes : **0 écart** également. `masks.png` reste en `uint8` sur tout
le corpus existant, au bit près, et `FORMAT_VERSION` ne bouge pas.

La seule sortie qui change est le **PSD d'un webtoon**, qui perd son calque de scan d'origine
(`manga.formats.webtoon.rendu.psd_original: true` le rend).

## [2.5.0] - 2026-08-25

### MINEUR — Les bulles doubles qu'on laissait passer, et le texte hors bulle lu à l'envers

Deux familles de défauts, réunies parce qu'elles partagent leur corpus et leur critère.

Le premier était **déjà entièrement documenté par le dépôt lui-même**. `RAPPORT.md` liste
depuis le lot 4.2 une section « Régions bi-lobées SUSPECTES, non scindées » — un goulot trouvé,
un découpage refusé —, avec la planche, le numéro de bulle, le remplissage et le texte. Sur les
cinq volumes du corpus, elle contient **33 entrées**. Il n'y avait rien à chercher : seulement à
mesurer ce qu'on en gagne, et à quel prix.

Le second est plus simple et plus vexant : le tri des zones de texte hors bulle était **codé en
dur** en droite→gauche. C'était le seul endroit de la chaîne à ignorer le sens de lecture du
format.

**Ce que la mesure donne, si on les active** (six volumes, rejeu sur les masques en cache) :
les régions bi-lobées suspectes non scindées passent de **57 à 14** — soit **−75 %** — et les
scissions de **49 à 90**, *sans qu'un seul faux positif apparaisse* — le compteur de bulles non nettoyées de
`RAPPORT.md` reste à 2/819, 0/778, 1/923 et 4/876 alors que le nombre de bulles augmente
partout. Le détail, le protocole et les limites sont dans
[`docs/mesures/doubles-2026-08-25.md`](docs/mesures/doubles-2026-08-25.md).

> **⚠ Les trois leviers de scission sont livrés INACTIFS.** Ils changent le *nombre de bulles*
> d'un tome déjà traité — ce que le mécanisme d'invalidation existant absorbe très bien
> (`invalider_textes` + `downstream("detection")`, aucun changement de `FORMAT_VERSION`) mais
> qui coûte une retraduction. À réglages par défaut, ce lot ne modifie **aucune** sortie de la
> brique, hormis les nouvelles sections de `RAPPORT.md`. Les correctifs hors bulle, eux, sont
> actifs : ils ne changent pas le nombre de zones, seulement leur ordre et leur traçabilité.

#### Exiger la STABILITÉ d'une scission — `manga.detection.scission.stabilite`

`scinder_par_erosion` balayait l'échelle d'érosion jusqu'à ce que le masque tombe en deux
composantes, puis validait **une seule fois** : si les garde-fous de forme refusaient les lobes,
la fonction abandonnait toute l'échelle. Le choix était assumé, et l'objection sérieuse —
continuer après un échec, c'est chercher un `k` qui passe les garde-fous, donc s'en servir comme
objectif de recherche au lieu de contrôle.

Mais c'est exactement ce qui produisait les 33 suspectes : un goulot large cède à `k = 3` en
donnant deux lobes déséquilibrés, alors qu'à `k = 5` il aurait donné deux lobes propres.

La sortie de l'impasse n'est pas « essayer jusqu'à ce que ça passe ». C'est **exiger la
stabilité** : un découpage n'est retenu que s'il se présente **identique sur `stabilite`
échelons consécutifs** — même nombre de lobes, et lobes appariés d'un `k` au suivant par IoU de
boîtes (`geometry.suivre_boites`, déjà écrit pour l'éditeur). Un vrai goulot produit une
scission robuste sur une plage de `k` ; un artefact de bruit produit une scission qui n'existe
qu'à un seul `k`. **C'est plus exigeant que le critère historique, pas moins** — et le test le
montre dans les deux sens : un masque construit pour ne se séparer qu'à `k = 8` est scindé par
le régime historique et refusé par le régime stable.

Le découpage rendu est le **premier échelon valide de la série**, donc l'érosion la plus douce :
la plus fidèle au masque d'origine.

Coût : `k_max` érosions au lieu d'un arrêt au premier succès. `erode` est en O(1) par axe
(sommes cumulées), donc le surcoût est **linéaire** en `k_max`, jamais quadratique.

#### Juger la compacité d'un lobe RELATIVEMENT au parent — `remplissage_lobe_relatif`

`remplissage_lobe_min: 0.72` vient d'une mesure honnête : les huit faux découpages du tome de
référence sont tous ≤ 0,71, les vrais doubles entre 0,72 et 0,91. Mais ce seuil **absolu** a un
angle mort : deux **ballons de cri** accolés — contour en étoile, très courant en action — ont
chacun un remplissage naturellement bien en dessous de 0,72. Ils ne sont donc *jamais* scindés,
quel que soit le `k`. Et ce sont précisément les bulles où deux personnages crient séparément,
donc où la fusion se voit le plus : les 38 « dentelées ou à longue queue » de *manga A* Vol.2 et
les 19 de *webtoon A* sont ce vivier.

En mode relatif, le seuil d'un lobe devient
`max(plancher, remplissage_lobe_relatif × remplissage du parent)`. Le critère passe de « les
lobes sont compacts dans l'absolu » à « **la scission ne dégrade pas la compacité** ». Un parent
à 0,60 accepte des lobes à 0,57 ; un parent à 0,89 exige des lobes convaincants.

`remplissage_lobe_plancher: 0.20` reste un plancher bas et très permissif, et il est contrôlé
**deux fois** — c'est un point que la mesure a imposé. `_valide` juge les lobes seuls, avant
absorption des restes, et c'est délibéré (un éclat de 200 px à l'opposé du masque faisait passer
la boîte d'un lobe de 44 000 à 91 700 px² et rejetait un découpage parfait). Le prix de ce choix
est qu'un lobe peut retomber sous le plancher une fois les restes recollés : **mesuré à 0,190**
sur *manga A* Vol.1. Le critère du lot porte sur les masques réellement écrits, pas sur ce que
la validation a vu — d'où un second contrôle, du seul plancher, après absorption.

#### Les trois valeurs qui étaient réellement en dur

`max_lobes`, `germe_frac` et `k_max` n'étaient dans **aucun** dictionnaire de défauts : les
écrire dans `config.yaml` n'aurait rien fait, **en silence** (`_config.fusion` filtre par clé
connue). Elles sont désormais configurables, à valeurs inchangées.

Et `max_lobes` n'est pas un rejet, c'est une **troncature des germes** : une grappe de cinq
ballons était ramenée à quatre, les pixels du cinquième repartant au lobe le plus proche. Sans
un mot nulle part. `RAPPORT.md` les compte désormais.

⚠ Correction d'une affirmation de l'ancien plan : `seuil_remplissage` et `seuil_suspect`, eux,
étaient **déjà** configurables.

#### L'aire minimale en fraction de planche — `aire_min_frac`

`aire_min: 10000` est en pixels, et sur un scan basse résolution — *manga D* est en
844×1200 — deux petites bulles collées de 90×90 font 16 200 px² ensemble et passent, tandis que
deux de 60×60 font 7 200 px² et ne sont **jamais examinées**. Le seuil n'exprime pas ce qu'on
veut dire. `aire_min_frac` l'exprime relativement à la planche, sur le motif de
`adaptive_radius` — donc en fraction du **carré du petit côté**, et surtout pas de l'aire. La
valeur iso-comportement sur la planche de référence est **0,0079**.

⚠ **Le petit côté, et pas l'aire** : sur un webtoon, « la planche » est une bande d'un chapitre
entier (1080 × 10 000), et une fraction d'aire y vaudrait 60 480 px² — six fois le seuil visé,
sur le format où les ballons sont déjà les plus petits. L'argument est aussi plus fort que le
plan ne le disait : *manga D* Vol.1 mélange **quatre tailles de planche dans un seul
tome** (844×1200, 1000×1200, 1030×732, 1688×1200).

⚠ Mesuré sur les six volumes, ce levier ne change **rien** : aucune région ne tombe dans la
bande nouvellement éligible. Il rend le seuil juste, il ne rapporte pas de bulle ici — et c'est
précisément pour qu'on ne l'active pas en croyant gagner quelque chose que le résultat est écrit.

#### Sonde d'ENCRE — une ÉVALUATION, avec son critère d'abandon écrit à l'avance

Toute la scission est morphologique. Or le **trait de contour** est un signal fort, présent et
gratuit — la chose la plus noire et la plus continue de la région —, et deux ballons accolés ont
**deux** contours qui se touchent : une ligne d'encre traverse la région exactement là où le
goulot se trouve. C'est aussi la réponse à un biais réel de l'érosion, dont l'élément
structurant est carré donc **anisotrope** : un goulot diagonal cède à un `k` environ 30 % plus
petit qu'un goulot droit de même largeur, si bien que le `k` retenu n'a pas la même
signification selon l'orientation. Le trait, lui, n'en a pas.

C'est le **seul point du lot dont le résultat est incertain**, et il est traité comme tel :
livré inactif, avec un critère d'abandon écrit dans `manga/bubbles_split.py` **avant** la
mesure — au moins cinq vrais doubles gagnés, et zéro faux positif, sinon la sonde saute.

En appui et jamais en remplacement : elle ne peut que relâcher le garde-fou de forme jusqu'au
plancher, sur un découpage que l'érosion avait **déjà** proposé. Un trait qui traverse sans
goulot est **signalé au rapport, jamais scindé d'autorité** — le principe directeur du projet
est que l'outil ne décide pas à la place de l'humain quand il n'est pas sûr.

La couture est interrogée là où elle est (`dilate(a,1) & b`), et non par un balayage de colonnes
qui rendrait à la sonde le biais anisotrope qu'elle vient compenser. Sur géométrie synthétique,
elle discrimine nettement : **86 %** d'encre sur la couture de deux ballons dont les contours se
rejoignent, **4,5 %** sur une coupe arbitraire d'un ballon unique.

#### L'ordre de lecture du texte hors bulle suit enfin le format — CORRECTIF

```python
# text_detection.py, avant
regions.sort(key=lambda r: (-r.bbox[2], r.bbox[1]))   # droite → gauche, en dur
```

`hors_des_bulles` n'avait aucun paramètre `sens`, alors que son unique appelant l'a sous la main
depuis toujours (`formats.sens_lecture`, calculé quarante lignes plus haut et utilisé à six
autres endroits). Sur un webtoon, les bulles étaient donc ordonnées correctement et **les
onomatopées numérotées à l'envers** : le rapport les listait dans un ordre qui ne correspondait
à rien, et le prompt de `_translate_sfx` les présentait au modèle dans cet ordre-là.

Le tri passe désormais par `ocr.reading_order`, la **même** fonction que les bulles — qui fait
de surcroît mieux qu'un tri par abscisse, puisqu'elle coupe en X-Y sur les gouttières. Entretenir
deux ordres de lecture dans le même pipeline est la dette qui a produit `tools/verifier_ordre.py`.

⚠ Le même défaut avait déjà été corrigé une fois, sur `document.poser_regions`.

**La portée est plus large que le webtoon**, et la mesure le dit : sur *manga A* Vol.1 — manga
paginé, sens `droite_gauche` — **77 planches sur 122** avaient leurs zones hors bulle dans un
ordre que la coupe X-Y n'aurait pas produit. Rien n'est re-détecté pour autant : les caches
existants gardent leur ordre (la passe ne se relance que si `sfx.json` manque), et quand elle se
relance, `save_sfx` compare les textes et invalide `sfx_traduction.json` de lui-même — le
mécanisme existe depuis la correction du crop.

`tools/verifier_ordre.py` couvre désormais les zones hors bulle en plus des bulles. Il ne
regardait que les secondes, ce qui suffisait à le rendre rassurant et faux sur ce défaut-là.

#### `_union_bulles` n'avale plus une incohérence de forme — CORRECTIF

```python
if m is not None and m.shape == forme:   # sinon : écarté sans un mot
```

Aucun `warn`, aucun compteur, aucun diagnostic. Et la cascade est brutale : l'union sort vide,
`union.any()` est faux, et **toutes** les répliques déjà prises en charge par une bulle sont
re-détectées comme texte hors bulle — relues par `manga-ocr`, retraduites en glose, listées au
rapport. Le cas arrive avec le fenêtrage, ou sur un cache écrit avant un changement de découpage.
C'est désormais compté, décrit (les formes en cause) et remonté dans `RAPPORT.md`, avec la
commande qui répare.

#### Ce que `RAPPORT.md` gagne

- **Régions à goulot INSTABLE** — un découpage qui s'ouvre puis disparaît d'un échelon à
  l'autre. Section séparée, et pour la raison qui a fait séparer les « dentelées » au lot 4.2 :
  ce n'est **pas** un double manqué, et le ranger avec eux les noierait.
- **Germes de lobe TRONQUÉS** par `max_lobes`, avec la région et le nombre.
- **Lobes VIDÉS par le rendu disjoint** — voir ci-dessous.
- **Régions traversées par un TRAIT sans goulot** et **scindées sur confirmation du trait**,
  quand la sonde est armée.
- **Masques de bulle de forme inattendue** écartés de l'appariement.

---

### Ce que la mesure a corrigé dans le plan

Trois affirmations du plan de lot ne survivent pas à la mesure. Elles sont consignées ici parce
qu'un plan qu'on n'a pas confronté au corpus est une intention, pas un résultat.

**1. Les lobes à 0,01 et 0,14 du webtoon ne viennent pas de la scission.** Le plan en fait le
critère de non-régression du seuil de forme. Or ce garde-fou exige **0,72** par lobe : il ne
*peut pas* émettre 0,01. Vérifié sur *webtoon A* Chap.11 page 1 — le détecteur avait émis
à la fois une région fusionnée (scindée en deux lobes) **et** les deux ballons séparément ;
`rendre_disjoints` a donné les pixels partagés aux mieux notés, laissant les lobes à 1 536 et
25 829 px. Un seuil de scission plus serré n'y aurait rien changé. La cause est le format de
`masks.png` — une image d'étiquettes, où un pixel ne peut appartenir qu'à une région.

Le garde-fou est donc posé **là où le défaut est** : les lobes vidés par le rendu disjoint sont
comptés et listés, sur les régions telles qu'elles seront écrites.

**2. `onomatopees.min_composante` n'est pas le levier de coût que le plan croit.** Le seuil
s'applique **après** la dilatation de groupement (~9 px), pas au masque d'encre. Mesuré : la
plus petite composante d'une planche synthétique réaliste pèse déjà **240 px²**, et le passage
de 1 à 128 ne change **ni le temps, ni la mémoire, ni le résultat** — sur une planche 1125×1600
comme sur une bande 1080×10 000. Pour mordre, il faudrait le monter au niveau d'`aire_min`,
c'est-à-dire dans la zone où il change le résultat — précisément ce que le plan interdit à juste
titre. La clé est livrée, documentée avec ce plancher réel ; elle n'est pas la réponse.

**3. Le coût de la passe hors bulle est ailleurs, et il est chiffré.** Mesuré sur une bande
1080×10 000 : **145 s** et **40,6 Go** de pic d'allocation. Le poste dominant est `composantes`,
qui matérialise **2 004 masques booléens pleine page** — 10,8 Mo chacun, soit ~21,6 Go à lui
seul. Deux allocations inutiles ont été supprimées ici (le `&` et le `|` remplacés par des
opérations en place, résultat identique au bit) : **1,6 %**. Le reste est structurel et relève
du masque local avec sa boîte — c'est le lot 14, et il a désormais sa mesure de départ.

---

### Corrigé

- Ordre de lecture des zones hors bulle : le sens du format était ignoré (onomatopées numérotées
  à l'envers sur tout webtoon).
- `_union_bulles` écartait un masque de forme inattendue sans le signaler, ce qui pouvait faire
  re-détecter, relire et retraduire toutes les répliques d'une planche comme texte hors bulle.
- `fusionner_proches` mutait la première composante de chaque groupe (elle la stockait par
  référence puis écrivait dedans) — sans conséquence observée, mais le genre de bogue qui se
  manifeste dix étapes plus loin.

### Ajouté

- `manga.detection.scission` : `stabilite`, `iou_stabilite`, `remplissage_lobe_relatif`,
  `remplissage_lobe_plancher`, `aire_min_frac`, `max_lobes`, `germe_frac`, `k_max`, et le
  sous-bloc `encre` (`actif`, `part_min`, `facteur_seuil`, `plancher_confirme`).
- `manga.onomatopees.min_composante`.
- `tests/test_manga_doubles_et_hors_bulle.py` — 42 tests, sans modèle ni corpus.
- `docs/mesures/doubles-2026-08-25.md` — la mesure, son protocole et ses limites.

---

## [2.4.0] - 2026-08-25

### MINEUR — Plus aucune planche muette : la détection escalade au lieu d'écrire un vide

Sur les dix volumes de `build/`, **188 planches sur 1 513 rendent zéro bulle** (12,4 %). Ce
n'était pas un défaut invisible : `RAPPORT.md` les comptait déjà, et les triait déjà. Ce qui
manquait n'était pas la mesure, c'était **l'escalade** — rien ne réagissait.

La machinerie de réparation existait pourtant, et elle était calibrée : `manga/detection_retry.py`,
un arbitre à quatre vétos ordonnés, écrit au lot 4.2. Elle avait **un seul site d'appel** —
`--conf` / `--iou` en ligne de commande, avec `--page` obligatoire — et `len(regions) == 0` ne
déclenchait rien du tout : entre la détection et l'arbitre, aucun test de longueur. Un
`regions.json` vide s'écrivait en silence, et comme `len(regions) != len(reference)` était faux
(0 == 0), l'invalidation des textes en aval n'avait même pas lieu.

#### La résolution d'entrée devient configurable — `manga.detection.input_size`

`INPUT_SIZE = 640` était une constante de module que **rien** ne remontait : ni paramètre de
`BubbleDetector.__init__`, ni clé de config. Or les poids téléchargés (`model_dynamic.onnx`)
sont un export à **axes dynamiques** — vérifié sur le fichier livré, l'entrée est déclarée
`['batch', 3, 'height', 'width']`. Le modèle acceptait d'autres résolutions ; le code n'en
proposait aucune.

Le seul levier proposé jusqu'ici contre les bulles trop petites était le **découpage en
fenêtres**, qui traite le symptôme sur une seule classe d'images et coûte **×9 en temps
d'inférence** (~70 s par planche contre ~8 s). Relever `input_size` à 1024 multiplie la
résolution effective par 1,6 sur **toutes** les planches — y compris les scans paginés basse
résolution (844×1200, 848×1200) où les petites bulles de fond arrivent sous 30 px — **sans une
seule inférence supplémentaire**.

- **Le défaut reste 640, et le comportement livré ne change pas d'un pixel.** Vérifié
  directement : à réglages par défaut, le post-traitement rend des boîtes et des masques
  **identiques au bit** à ceux du code d'avant le lot, sur les planches 136 et 142 de *manga A*
  Vol.1 (celles qui portent le plus de scissions).
- La résolution est un paramètre **par appel** autant qu'une clé de config : c'est ce qui
  permet de relancer une planche à 1024 sans reconstruire le détecteur, donc sans recharger
  104 Mo de poids.
- Une valeur hors stride est **arrondie au multiple de 32 et annoncée** ; un modèle à axes
  figés est refusé par un message qui nomme la clé, la valeur et le fichier, plutôt que par une
  erreur d'algèbre d'ONNX Runtime à la première planche.
- `tools/apercu_detection.py --resolutions` balaie les résolutions et **affiche le temps de
  chacune** : les seuils sont gratuits (une inférence, douze post-traitements), la résolution
  ne l'est pas.

#### L'escalade — `manga.detection.escalade`, **livrée active**

Une planche est *suspecte* quand elle contredit ses voisines. Elle reçoit alors une seconde
inférence à `input_size: 1024` et `conf_threshold: 0.20`, et l'arbitre décide.

Deux déclencheurs, par ordre de certitude :

1. **zéro bulle sur une planche qui porte de l'encre** — le cas des 188 planches ;
2. **très en dessous de la médiane de bulles du tome** (`mediane_frac: 0.25`), armé seulement
   après 20 planches vues : les médianes mesurées vont de 3 à 6, donc une planche à 1 bulle
   dans un tome à médiane 6 mérite un second regard.

> Un troisième déclencheur figurait au plan — « le masque du détecteur de texte voit du texte
> là où aucune bulle n'est détectée ». Il n'est **pas** écrit, et la raison est dans
> `detection_retry.MOTIFS_ESCALADE` : sur une planche à zéro bulle il désignerait un
> sous-ensemble du déclencheur 1, qui escalade déjà ; sur une planche qui porte des bulles, il
> décrit du texte hors bulle — le sujet d'un autre lot. Il coûterait une passe ONNX de 94,7 Mo
> par planche suspecte et ne serait disponible que si la passe onomatopées tourne.

#### Le chiffre du lot, mesuré sur les dix volumes

Rejoué planche par planche et **sans rien réécrire**, avec la même fabrique de détecteur, la
même scission, les mêmes masques disjoints et le même arbitre que le pipeline —
[`docs/mesures/escalade-2026-08-25.md`](docs/mesures/escalade-2026-08-25.md) :

| | avant | après |
|---|---|---|
| Planches à zéro bulle (sur 1 513) | **188** | **153** — −18,6 % |
| …dont porteuses d'encre | **183** | **148** — −19,1 % |

**35 pages entièrement non traduites portent désormais du texte, pour 47 bulles gagnées**, et
**les neuf volumes paginés gagnent tous quelque chose** : ce n'est pas un tome qui porte le
résultat. Sur les 183 planches suspectes, l'arbitre a accepté 35 fois, refusé 146 fois faute de
la moindre candidate, et 2 fois parce que tout ce qui avait été trouvé était du dessin — le véto
en action.

**⚠ Et la seconde moitié du critère : zéro régression.** Aucun `bulle_perdue`, aucune
`explosion`, aucun `chevauchement`, aucun `masque_gonfle`. Par construction, les 1 325 planches
qui allaient bien ne reçoivent pas de seconde inférence du tout.

> **La réserve, nommée plutôt que masquée.** Une couverture n'est **pas** une page blanche —
> elle s'écarte du fond sur 72 à 99 % de ses pixels —, donc l'escalade s'y arme, légitimement.
> Elle en tire **6 des 47 bulles**, sur 5 liminaires de *manga A*, et **ces six-là n'ont pas été
> inspectées à l'œil** : un cartouche de titre et une fausse détection sur un aplat se
> ressemblent dans un tableau. Le décompte principal — 35 planches réparées — n'en dépend pas,
> et le garde-fou est déjà en place (le nettoyeur refuse une région sous `seuil_abandon`, et
> `RAPPORT.md` publie « zones restaurées » et « bulles sans texte OCR »), mais c'est par là
> qu'un relecteur devrait commencer.

**Ce que ça coûte :** une inférence de plus sur les planches suspectes **seulement**. Mesuré de
bout en bout — détection nominale, seconde inférence, et les deux analyses d'uniformité que
l'arbitre demande — **5,5 s par planche suspecte**, soit 1 002 s pour les 183 planches des dix
volumes. Le *surcoût* en est une fraction : la détection nominale était payée de toute façon.
Rapporté au temps total d'un tome (*manga A* Vol.2 : **46 min 56 s** pour 150 planches, dont
l'essentiel en LLM et en PSD), c'est du bruit — la détection n'est pas l'étape chère. **Ce que ça ne coûte pas :**
aucun cache n'est invalidé. Une planche déjà détectée est sautée comme avant ; l'escalade ne
joue que sur une détection fraîche. `escalade.actif: false` rend exactement le comportement
d'avant.

> **Ce que la mesure ne dit pas**, et c'est écrit dans le document : elle ne balaie pas
> 640/800/1024/1280 sur les 1 513 planches (un run de plusieurs heures — `--resolutions` rend la
> courbe planche par planche), et elle ne mesure pas les faux positifs par leurs **conséquences**
> (zones restaurées, bulles sans texte OCR, bulles non nettoyées), qui demandent un run complet.

#### Un test d'encre qui ne dépend plus de la passe onomatopées

Le seul discriminant entre « page de garde » et « pleine page d'action » était
`bool(qa["sfx"])`. Il est correct pour ce que le rapport en dit, et il est **indisponible dès
que la passe onomatopées ne tourne pas** : les trois volumes de *manga D* du corpus
n'ont **aucun** `sfx.json`, et leurs 72 planches à zéro bulle n'étaient triées **du tout**.

`manga.detection.porte_de_l_encre` répond sans modèle, sans E/S, sur l'image sous-échantillonnée
×4 : le fond est la luminance **médiane** et non le blanc, pour qu'une planche inversée ou un
webtoon couleur ne soient pas déclarés couverts d'encre d'office. `tools/_banc_commun.py` s'y
adosse désormais plutôt que d'en garder une copie — **le même test** arme l'escalade et remplit
la colonne « dont encrées ». Un rapport qui trierait ses planches autrement que le pipeline ne
mesurerait pas le pipeline.

**Résultat mesuré : les 188 planches à zéro bulle sont désormais toutes classées** — 183
portent de l'encre, 5 sont blanches, **0 non mesurée**, contre 140 / 5 / **43** au tableau du
2026-08-25. Les 43 manquantes sont débloquées par une quatrième source d'image consultée en
dernier recours, `sources/` : c'est la seule entorse au « cache-seul » du banc, et elle est en
lecture. Iso-comportement vérifié : sur les 145 planches déjà mesurables, le verdict est
inchangé pour **toutes**.

> ⚠ **Une prémisse du plan était fausse, et elle est corrigée dans
> [`docs/chiffres-de-reference.md`](docs/chiffres-de-reference.md).** Le plan donnait les
> planches 1 à 4 et 147 à 150 de *manga A* pour des « négatifs attendus ». Mesuré, une
> couverture s'écarte du fond sur **88 à 99 %** de ses pixels — c'est une illustration pleine
> page. Un seul de ces huit feuillets est réellement blanc, la planche 2, et le test la classe
> correctement sur les quatre tomes. L'escalade tournera donc sur les couvertures, pour une
> inférence chacune dont l'arbitre ne retiendra rien.

#### Nouveaux garde-fous de détection, et la fin de trois silences

- **`manga.detection.aire_min_frac`** — aire minimale en **fraction de la planche**, jamais en
  pixels. Le seul filtre géométrique du post-traitement était « moins de 2 px de côté » : une
  détection de 10×10 px à score 0,36 survivait à tout, traversait l'ordre de lecture, l'OCR
  (agrandie ×2 puis lue — du bruit) et **occupait une place numérotée dans le prompt du
  traducteur**, décalant toute la planche. Livrée à `0.0` — la clé arrive avec son
  instrumentation, sa calibration se fait au banc.
- **Un masque vide est enfin rejeté.** Le recadrage sur la boîte peut vider entièrement un
  masque bruité ; la région partait quand même dans `regions.json`, et c'est en aval seulement
  que `clean.analyze_bubble` la neutralisait — trop tard pour lui épargner l'OCR, l'appel LLM
  et sa place numérotée.
- **Les rejets sont comptés par motif** (`detection.MOTIFS_REJET`) et publiés dans
  `RAPPORT.md`. Un filtre muet est la façon dont on perd les treize planches suivantes.
- **Les bulles rognées par une voisine remontent au rapport**, avec leur boîte et l'aire cédée.
  Elles n'étaient signalées qu'en `warn` — donc dans `perf.log`, où personne ne les relit — et
  **après** que `save_regions` avait déjà écrit. La troncature à six entrées reste sur le
  `warn` ; le rapport, lui, les liste toutes. La cause n'est pas la détection mais le format de
  cache (`masks.png` est une image d'étiquettes) : la vraie réparation demande de le changer.
- **Et l'arbitrage de ces pixels a été mesuré, pas argumenté.** Score, aire et compacité rejoués
  sur 125 planches de cinq volumes, dont 15 portent un recouvrement réel : l'aire cédée est la
  même dans les trois cas (344 939 px — elle dépend de la géométrie, pas de l'ordre), et
  **14 des 15 sont rigoureusement équivalentes**, y compris le plus gros recouvrement paginé
  (166 146 px). La quinzième est un webtoon, où trier par aire laisserait zéro région non
  nettoyable contre une pour le score. **Le score est conservé** : basculer sur une seule
  observation serait le réglage à l'aveugle que ce dépôt évite. Détail dans
  [`docs/mesures/escalade-2026-08-25.md`](docs/mesures/escalade-2026-08-25.md).

#### Coutures de fenêtres : containment de masques, plus IoU de boîtes

Avec les défauts livrés, une bulle de 500 px à cheval sur une couture est vue tronquée par une
fenêtre (160 px) et entière par la suivante. Leur IoU vaut 160/500 = **0,32**, sous le seuil :
les deux étaient conservées. La tronquée ressortait de `rendre_disjoints` en sliver et produisait
une bulle vide de plus, un OCR de plus, et **une réplique numérotée de plus attendue du LLM**.

Une candidate marquée couture contenue à ≥ 0,85 dans une candidate **entière** est désormais un
doublon, quel que soit l'IoU — le critère que `text_detection.hors_des_bulles` défend déjà dans
ce dépôt. ⚠ Le seuil d'IoU n'est **pas** touché : c'est le même paramètre que le NMS
intra-fenêtre, et le déplacer ici le déplacerait là. La doctrine reste entière : on ne jette
une coupée que quand sa version entière est là.

#### L'arbitre : deux régimes explicites, et un critère qui acceptait un masque gonflé

- **Régime « référence vide ».** Avec `reference == []`, tout le registre de vétos se désarmait
  de lui-même — `bulle_perdue` ne peut pas s'armer, `explosion` est court-circuité par le
  premier terme de sa conjonction, la porte d'acceptation s'ouvre. Et à l'étage au-dessus,
  `if reference and not verdict.accepte` **sautait le bloc de refus** : la trace affichait
  « REFUSÉ » juste avant que `save_regions` écrive quand même. Une branche explicite s'y
  substitue : l'arbitre **sélectionne** candidate par candidate sur le seuil d'abandon du
  nettoyage — une bulle nettoyable est une bulle, une bulle qu'on ne sait pas peindre est du
  décor — et son refus est aussi contraignant qu'ailleurs.
- **Nouveau motif `masque_gonfle`.** Le dernier critère acceptait toute hausse du remplissage
  moyen. Or le remplissage monte pour deux raisons opposées : la boîte a rétréci autour du même
  masque (la bulle est mieux cernée) **ou** le masque a grossi dans la même boîte (la région a
  avalé du décor). `geometry.py` établit dans ce même dépôt qu'un remplissage bas signale un
  vrai double (0,61 et 0,60 contre une médiane de 0,89) : un masque qui gonfle va dans le sens
  de la perte d'information. Seul le premier cas est désormais accepté.
- Un correctif « refuser si le nombre de régions a baissé » aurait été **inerte** à cet
  endroit, et le module dit maintenant pourquoi : `apparier` étant injectif, l'appariement y est
  une bijection par construction, et une fusion de deux ballons est déjà refusée en amont par
  `bulle_perdue`.

#### Choix documentés plutôt que faits

- **`document.poser_regions` n'est PAS aligné sur le tri par score** du chemin de détection, et
  le module dit pourquoi en trois points : une région tracée à la main naît à `score = 1.0`
  (donc le score n'y discrimine rien), l'arbitre y est l'utilisateur via `touchees`, et un tri
  global ferait céder ses pixels à une bulle que l'édition ne touche pas — une amputation à
  distance sur une planche qu'on croyait ne pas avoir modifiée.
- **Le second détecteur sous licence permissive n'a pas été évalué.** Cela demande de
  télécharger des poids tiers, et le protocole est écrit dans
  [`manga_models/README.md`](manga_models/README.md) : les deux candidats `ogkalu` sont
  Apache-2.0 et entraînés sur du webtoon, et l'un d'eux a `imgsize: 1024` — ce qui est
  précisément le levier que ce lot vient de rendre configurable sur le détecteur actuel. Il faut
  savoir ce que la résolution seule a déjà donné avant d'ajouter 100 Mo au projet.

#### Une dette de commentaire soldée

`detection.py` et `config.yaml` annonçaient qu'une bulle de webtoon de 400×500 arrive au réseau
en **27×34 px**. À un facteur de letterbox de 0,0640, le calcul donne **26×32** (27×34
correspondrait à r ≈ 0,0676). La conclusion ne bouge pas — « ~3×4 cellules au stride 8, sous le
seuil d'émission de YOLOv8 » — mais un chiffre faux dans un commentaire qui **sert d'argument**
est une dette. Corrigé aux six emplacements vivants ; les entrées de changelog antérieures sont
laissées telles quelles, un journal ne se réécrit pas.

## [2.3.0] - 2026-08-25

### MINEUR — La passe onomatopées est activée dans la configuration livrée

`manga.onomatopees.actif` passe à `true`. Le texte posé **sur le dessin** — onomatopées
géantes d'une page d'action, narration en colonne dans un blanc de case — est donc détecté,
lu et traduit par défaut.

**Ce que ça coûte, dit franchement :**

- **94,7 Mo** de poids téléchargés une fois (`comic-text-detector`, cf. `manga_models/`) ;
- une passe ONNX de détection de texte **par planche** ;
- en mode `"rapport"` — le défaut, inchangé — **un appel LLM par planche portant du texte hors
  bulle**, pour le lire et le traduire.

**Ce que ça ne coûte pas :** aucun cache n'est périmé. `sfx` est dans
`checkpoints.CACHE_NON_BLOQUANT`, ne dépend que de `detection` et ne nourrit que `rendu` :
l'activer sur un tome déjà traduit ne relance ni l'OCR des bulles, ni la traduction de planche.

**Rien n'est dessiné sur les planches.** Le mode reste `"rapport"` : on détecte, on lit, on
traduit, et on n'écrit que dans `RAPPORT.md`. La raison est inchangée et elle est mesurée — la
DÉTECTION du texte hors bulle est fiable, la LECTURE ne l'est pas (`manga-ocr` est un modèle de
dialogue et hallucine sur une onomatopée stylisée). Passer à `"glose"` reste un geste explicite.

> ⚠ **Le défaut du CODE reste `False`, et ce n'est pas une contradiction.** Il ne s'applique
> qu'à un `config.yaml` où le bloc `onomatopees` est entièrement **absent** — configuration
> antérieure au lot 9, config minimale, fixture de test. La ligne livrée dit ce que le projet
> recommande à qui la lit ; le défaut de repli dit quoi faire quand personne n'a rien choisi, et
> il se juge sur ce qu'il coûte quand on se trompe : déclencher 94,7 Mo de téléchargement sans
> qu'on l'ait demandé. Le commentaire de `orchestrator_manga.py` disait « le défaut du code doit
> être celui de la configuration livrée » ; c'est cette phrase qui était trop courte, pas le
> défaut.

**Effet de bord attendu, et souhaitable.** Les volumes traités sans cette passe n'ont aucun
`sfx.json`, si bien que `RAPPORT.md` ne trie pas leurs planches à zéro bulle entre page de garde
et pleine page d'action (cf. `docs/chiffres-de-reference.md`, piège n° 2). Les tomes traités à
partir d'ici seront triés. Le banc, lui, ne dépend pas de cette passe : il mesure l'encre sur
`pages_out/`.

## [2.2.0] - 2026-08-25

### MINEUR — Rebrancher ce qui était déjà écrit

Sept mécanismes étaient écrits, documentés, parfois mesurés — et **inertes**. Le fil commun :
le pipeline a plusieurs chemins, et les garde-fous n'avaient pas suivi. Chaque défaut ci-dessous
est un chemin qui avait divergé de son jumeau.

Aucun cache n'est invalidé, aucune clé de configuration n'est supprimée, aucune ligne de
commande ne change. **Ce lot ne gagne aucune bulle** : il rend au traducteur le contexte qu'on
avait déjà décidé de lui donner.

> ⚠ **Le prompt concerné est `manga/orchestrator_manga.py`, fonction `_translate_page`** — la
> liste `parts` du message utilisateur. La règle de numérotation de ce fichier range toute
> réécriture de prompt qui change le caractère de la traduction dans les MINEURs, et demande
> que l'entrée nomme le fichier. Les autres corrections de ce lot seraient des CORRECTIFS et
> peuvent partir seules.

#### La fiche de contexte n'atteignait jamais le chemin par défaut

`_translate_page` déclarait `contexte_oeuvre` **au paramètre** et ne le lisait **jamais** dans
son corps. Et pas seulement pour les tomes traduits par lots : sur le chemin par défaut
(`manga.lot.planches: 1`), `groupes_de_lot` rend des groupes d'une planche, le garde
`len(groupe) > 1` n'est jamais franchi, et `_translate_lot` — le seul consommateur de la fiche —
**n'est même pas appelé**.

Pendant ce temps `_passe_contexte` dépensait un appel LLM par tome, écrivait
`.checkpoints/contexte.txt` et affichait « injectée dans chaque planche ». Les huit fiches sont
dans `build/`, produites et jamais lues.

Ce n'est pas de la plomberie : `langues/fr/prompts/manga_contexte.md` demande au documentaliste
exactement ce qui manquait au traducteur — « **Adresse entre personnages** : qui vouvoie qui,
qui tutoie qui […] un vouvoiement qui change au milieu d'un tome se voit immédiatement ». Le
seul mécanisme du projet qui porte le registre était débranché sur le chemin que tout le monde
emprunte.

La fiche est désormais posée **en deuxième position**, après le glossaire et avant les répliques
précédentes — l'ordre du chemin par lots. Il n'est pas cosmétique : la fiche est une consigne de
voix, les répliques précédentes en sont des exemples.

**Le surcoût de prefill, mesuré.** `config.yaml` annonçait « 400 tokens × 131 planches =
52 000 tokens (+16 %) » — une estimation **au plafond**, et qui n'avait jamais été payée
puisque la fiche n'arrivait nulle part. Compté sur les huit `contexte.txt` réellement produits :
une fiche pèse **174 à 261 tokens** (médiane 219), et sur le tome de référence
255 × 131 = **33 405 tokens**, soit **+10,5 %** des 318 390 tokens du tome. C'est un compte de
tokens de l'énoncé — il ne dépend ni du modèle ni de la température, et se refait sur le cache
sans un seul appel LLM.

#### Le prompt annonçait une planche et en recevait trois

`manga.contexte.planches_precedentes` vaut **3** ; le prompt de planche disait « Répliques de
**la planche précédente** ». Le modèle recevait N−3, N−2 et N−1 en croyant qu'elles venaient
toutes de N−1 — sur un enchaînement de dialogue, exactement l'indication qui lui fait continuer
une phrase qui n'existe pas. Le chemin par lots avait le pluriel juste depuis toujours.

#### Le pack de langue n'atteignait pas le rattrapage unitaire

`traduction_unitaire.CLE_CONSIGNE` est le **seul** point d'externalisation de consigne du chemin
manga — et son unique appelant ne passait pas le pack. Pire : le code écrivait
`resoudre_pack(config).accorder()`, donc **jetait le pack** aussitôt construit. Pour toute cible
non française, le rattrapage réclamait une traduction **française** par une consigne codée en
dur, au beau milieu d'un run anglais.

Le pack est maintenant retenu par `process_volume` et traverse `_rattraper_bulles` jusqu'à
`traduire_bulle`. **Le même défaut existait dans l'éditeur graphique** — le bouton « retraduire
cette bulle » passait par la même fonction sans pack ; `Services.pack()` le résout une fois par
session.

#### `onomatopees.actif` : le code disait `true`, la config livrée dit `false`

Un `config.yaml` amputé du bloc `onomatopees` — fichier utilisateur antérieur au lot 9,
configuration minimale, fixture de test — activait donc **en silence** une passe qui télécharge
94,7 Mo de poids et ajoute une passe OCR complète sur tout le tome. Le défaut du code est
désormais celui de la configuration livrée.

#### Deux définitions du CJK selon la porte d'entrée

`diagnostiquer_rattrapage` utilisait `tokens._CJK` — la classe **large**, et au passage une API
**privée** du socle — là où `_source_residuelle` et le comptage utilisent `tokens.CJK_TEXTE`, la
classe étroite. La large englobe la ponctuation pleine chasse (`（）`, `「」`, `！`) : le
rattrapage rejetait donc des réponses que le chemin de planche acceptait. Une réplique
parfaitement traduite mais ponctuée `！` était refusée et **la bulle restait vide** — l'inverse
exact de ce que le rattrapage existe pour faire.

#### Le budget de caractères divergeait entre les deux chemins

`_lignes_gabarits` calculait `surface / 320` **sans jamais borner par la longueur de la
source** ; `traduction_unitaire.prompt_bulle` bornait. `surface / 320` est calibré sur du
japonais, qui est dense : d'une source latine vers le français, le gabarit de surface seul
demande au modèle d'être trois fois plus bavard que l'original.

Le seul webtoon du dépôt est à source **anglaise** (`webtoon A` Chap.11) : **tout son
lettrage de planche recevait le budget japonais non borné**, et seul le rattrapage unitaire
était juste. Le calcul vit désormais dans `traduction_unitaire.budget_caracteres`, un seul
point — la signature de `_lignes_gabarits` a dû changer pour recevoir les sources et la langue,
elle ne les recevait pas.

#### Une clé de configuration à `null` ne fait plus disparaître son défaut

`{**_DEFAUTS, **(cfg or {})}` recouvre les défauts **par toutes les clés présentes**, `None`
compris — or `null` est la façon normale d'écrire « laisse le défaut » en YAML. Le défaut était
alors remplacé par `None` et le premier `int()` levait.

Le motif est remplacé par `manga/_config.py:fusion`, généralisation du plus strict des deux
motifs corrects que la brique portait déjà (clé **connue** *et* valeur **non nulle**).

> ⚠ **Le relevé annonçait sept sites ; il y en avait dix.** `manga/gloss.py` portait le même
> motif et n'était pas dans la liste ; et les deux `_cfg` historiques (`clean`,
> `bubbles_split`) restaient deux copies de plus, dont une — `clean` — gardait `None` mais pas
> la clé inconnue. Un test garde la porte fermée.

#### Le recouvrement de fenêtre est borné, et le rabot est annoncé

La seule borne de `fenetre_recouvrement` était `h - 1`, ce qui n'en est pas une : avec
`fenetre_recouvrement: 2159` pour une fenêtre de 2160, le pas tombe à 1 px et une bande de
1080×10 000 produit **7 841 fenêtres** — donc 7 841 inférences ONNX pour une seule planche, sans
un avertissement. Le recouvrement est raboté à 80 % de la hauteur de fenêtre (20 fenêtres au
lieu de 7 841), et le rabot est **dit**, une fois par tome. Le réglage livré (900 sur 2160) est
très en dessous de la borne et ne déclenche rien.

#### L'inventaire des prompts en dur est complet

`docs/mesures/inventaire-couplage-fr.md` §5 annonçait « ces six sites » sans en citer **une seule** du
chemin manga hors `traduction_unitaire.CONSIGNE` : son relevé s'arrêtait aux constantes nommées
et ne descendait pas dans les f-strings assemblées dans les listes `parts`. Dix sites de plus y
sont maintenant nommés, fichier et ligne — **seize au total, dont un seul surchargeable par un
pack**. Ce lot ne les externalise pas : c'est l'objet du lot 15, qui n'aura plus à refaire le
relevé.

#### Au passage

`docs/roadmap.md` annonçait « Current version: 1.8.0 » sans dire que 2.0.0 était en cours sur sa
branche ; les jalons non publiés glissent d'un cran pour laisser 2.1.0 à ce lot.

35 tests neufs dans `tests/test_manga_chemins_rebranches.py`, un par étape, chacun comparant
**les deux chemins** plutôt qu'un seul — un test qui n'aurait regardé que `_translate_lot` serait
resté au vert pendant tout le temps où `_translate_page` perdait la fiche. Suite complète :
2 262 collectés, 2 206 dans la boucle courte, tous passés.


## [2.1.0] - 2026-08-25

### MINEUR — Le socle de mesure : `tools/banc.py`, un corpus annoté, un garde-fou en CI

Le projet avait de bons chiffres et les citait. Ils étaient réels. Mais **aucun ne mesurait la
détection** : ils mesuraient ce que le pipeline avait fait des bulles qu'il avait *vues*. Et
cinq nombres circulaient pour le même tome — 821, 813, 797, 790, 687 — tous exacts, aucun avec
son dénominateur écrit.

Rien du chemin nominal ne change. Aucun cache n'est invalidé, aucune clé de configuration
n'est touchée, aucune ligne de commande existante n'est modifiée.

#### `tools/banc.py` — une commande, tous les volumes, un tableau daté

```powershell
python tools/banc.py --tous --markdown > docs/mesures/banc-2026-08-25.md
python tools/banc.py --tous --traduction        # le banc de traduction, sans appel LLM
python tools/banc.py --corpus tests/corpus/synthetique   # rappel / precision / F1
```

`RAPPORT.md` mesurait **déjà** l'essentiel — planches à zéro bulle, détections faibles, régions
bi-lobées, zones restaurées, motifs d'échec résiduels, stratégie de rattachement. Mais par
tome, sans date et sans commit : rien n'agrégeait ces sections entre volumes, et deux runs ne
se comparaient pas. Le défaut n'était pas l'absence de mesure, c'était l'absence de tableau.

Chaque sortie `--markdown` porte la date, le commit, la version du dépôt et **l'empreinte
SHA-256 de `config.yaml`** : deux tableaux ne se comparent que si l'on sait ce qui a changé
entre eux.

**Deux pièges mesurés, que le banc ne reproduit pas :**

- **Les bulles ne se comptent pas depuis `qa.json`.** C'est ce que fait `RAPPORT.md`, et c'est
  pourquoi il annonce 813 bulles là où `regions.json` en porte 821 sur le tome de référence.
  Le banc compte depuis `regions.json` et publie les planches sans `qa` dans une colonne à
  part — 423 sur les 1 513 du corpus, dont 419 sur deux volumes qui n'ont **aucun**
  `RAPPORT.md`.
- **`qa["sfx"]` n'est pas un test d'encre.** La passe onomatopées est optionnelle ; sur un
  tome traité sans elle, aucune planche à zéro bulle n'est triée — une page de garde et une
  pleine page d'action y comptent pareil. Le banc mesure l'encre sur `pages_out/` et ne
  retombe sur `qa["sfx"]` qu'à défaut, en disant toujours laquelle des deux a répondu.

#### `tools/_banc_commun.py` — la lecture de cache, une seule fois

Quatre outils lisaient déjà `.checkpoints/`, chacun avec sa copie du calcul du dossier, de
l'énumération des planches et de la lecture des JSON. `mesurer_bulles.py`,
`apercu_detection.py`, `compter_variantes.py` et `verifier_ordre.py` passent tous par le
module partagé — **sans qu'aucun de leurs arguments ne change**. C'est la leçon que
`detection.depuis_config` avait déjà tirée pour la construction du détecteur.

#### Un corpus annoté, redistribuable sans réserve

`tools/corpus_synthetique.py` génère `tests/corpus/synthetique/` à graine **figée et publiée**
(`20260825`) : trois planches, 22 bulles annotées au format **COCO instance segmentation**,
sous **AGPL-3.0-or-later**. Bulle minuscule, ballon de cri, récitatif, double collé, bulle à
cheval sur un trait de case, et une **bande de 1080×10 000** — la seule planche du dépôt qui
exerce le découpage en fenêtres.

Aucun format n'a été inventé, et `_banc_detection.ecrire_cache_verite` écrit la même vérité au
format du pipeline (`regions.json` + `masks.png`) : une vérité terrain qu'on ne peut pas ouvrir
avec ses outils habituels n'est vérifiée par personne.

⚠ L'appariement passe par `detection_retry.apparier`, pas par une réimplémentation : glouton,
à IoU de masques ≥ 0,50. Deux implémentations mesureraient deux choses.

#### La première mesure, et ce qu'elle dit

`docs/mesures/banc-2026-08-25.md` — précision **1,00**, zéro fausse détection, zéro planche annotée
rendant zéro bulle, rappel **0,82**. Et le chiffre qui compte : **le rappel est de 0,00 sur les
bulles de moins de 2 000 px²**. La bulle minuscule n'est détectée sur aucune des trois
planches. C'était l'angle mort visé par le réglage d'`input_size` ; c'est désormais chiffré au
lieu d'être supposé.

#### Un garde-fou en CI

`tests/test_banc_corpus_synthetique.py` (job `banc` de `.github/workflows/ci.yml`) **casse le
build si le rappel baisse ou si les faux positifs montent** — les deux, parce qu'un lot qui
gagne des bulles en gagnant autant de fausses détections n'améliore rien, et qu'un seuil sur le
seul rappel le laisserait passer en affichant un succès. Sur 22 bulles annotées, **en perdre
une casse le build**.

Job séparé, et il le faut : le job `tests` exclut délibérément `modeles`. Marquer le banc
`modeles` sans ce job aurait écrit un garde-fou que la CI n'exécute jamais.

⚠ La ligne de base (`tests/corpus/synthetique/reference.json`) **se recalibre à la main** : un
banc qui réécrit sa propre référence à chaque run ne mesure plus rien.

#### Les chiffres du projet portent désormais leur dénominateur

`docs/chiffres-de-reference.md` dit ce que compte chaque nombre, avec sa source, sa date et la
commande qui le refait. Les chiffres périmés sont **corrigés ou datés**, jamais effacés :

- `manga/text_detection.py` — le « 1 593 » garde son chiffre historique et gagne son
  dénominateur (bulles des `qa.json` des deux tomes, **rendus de la v1.0.0**) ;
- `manga/bubbles_split.py`, `manga/geometry.py` et `config.yaml` se citent désormais l'un
  l'autre sur l'**écart 797 / 790**, qui n'est expliqué nulle part et qui se tranche en
  remesurant, pas en relisant ;
- le nombre de tests passe de « 1 908 » / « 1 657 » à **2 227**, daté du 2026-08-25 et
  accompagné de la commande qui le reproduit (`README.md`, `CONTRIBUTING.md`,
  `docs/COMMANDES.fr.md`) ;
- `manga_models/README.md` — la licence du détecteur de bulles
  (`kitsumed/yolov8m_seg-speech-bubble`) n'est plus « à vérifier » mais **GPL-3.0**, relevée le
  2026-08-25 et reportée dans `docs/ai-provenance.md`.

#### Le tableau « avant », publié et daté — et trois écarts expliqués

`docs/mesures/banc-2026-08-25.md` : les **dix volumes de `build/`**, 1 513 planches, 7 862 bulles.

- **188 planches rendent zéro bulle**, dont **140 portent de l'encre** — des pages entièrement
  non traduites, désormais chiffrées sur tout le corpus et non tome par tome.
- **423 planches n'ont aucun `qa.json`**, dont 419 sur deux volumes qui n'ont même pas de
  `RAPPORT.md`. Leurs bulles étaient comptées et n'étaient contrôlées par rien.
- **Le webtoon est un autre régime, et l'écart est massif** : 11 zones restaurées et 12 bulles
  sans OCR sur 59 bulles (19 % et 20 %), contre **zéro** de l'un comme de l'autre sur les
  7 803 bulles des neuf volumes de manga paginé.

Les écarts avec les `RAPPORT.md` se réconcilient au chiffre près, et l'un d'eux est une
**erreur de lecture** que la mesure a levée :

> `RAPPORT.md` écrit « ⚠ SANS contrôle qualité : 8 », et cette liste énumère des **numéros de
> planche**, pas un compte. Il n'y a pas huit planches sans contrôle qualité sur *manga A*
> Vol.1 : il y en a **une**, la page 8 — qui porte exactement 8 bulles. La coïncidence des deux
> nombres rendait la méprise invisible ; elle expliquait à tort l'écart 821 / 813 depuis des
> mois.

Nouveaux fichiers : `tools/banc.py`, `tools/_banc_commun.py`, `tools/_banc_detection.py`,
`tools/corpus_synthetique.py`, `tools/__init__.py`, `docs/procedures/banc-de-mesure.md`,
`docs/chiffres-de-reference.md`, `docs/mesures/banc-2026-08-25.md`, `tests/corpus/synthetique/`,
`tests/test_tools_banc.py`, `tests/test_banc_detection.py`,
`tests/test_banc_corpus_synthetique.py` (52 tests neufs).

## [2.0.0] - 2026-08-25

### ⚠ MAJEUR — Glossaire multi-cibles

**Le format de `glossaire.yaml` change.** Une migration automatique s'en charge à la première
lecture, avec une sauvegarde `glossaire.yaml.avant-multicibles.bak` écrite AVANT toute
réécriture — mais un glossaire migré n'est plus relisible par une version antérieure.

Le schéma n'avait qu'UN emplacement pour le rendu, `nom`, et rien n'y disait dans quelle langue
il était écrit. Tant que le projet ne produisait que du français, c'était sans conséquence.
Depuis les packs de langue cible, deux tomes de la même œuvre traduits vers deux langues se
disputaient ce champ : le second écrasait le premier, en silence.

```yaml
personnages:
  - termes_source: [魔王]
    description: Souverain des armées du gouffre.
    cibles:
      fr: {nom: Roi-démon, pluriel: Rois-démons, genre: masculin}
      en: {nom: Demon King}
```

Sous `cibles.<code>` : ce qui décrit le **rendu** (`nom`, `pluriel`, `genre`, `variantes`,
`interdits`, `force`). Au niveau de l'entrée : ce qui décrit **l'entité** (`termes_source`,
`traduire`, `role`, `description`).

⚠ **Enregistrer dans une cible n'efface pas les autres** — l'invariant qui justifie tout le
format. L'appariement se fait par `termes_source` d'abord : deux cibles n'ont pas le même `nom`
pour la même entité, et s'apparier par `nom` créerait un doublon par langue.

Migration vérifiée sur des **copies** des quatre glossaires réels du dépôt : 207 entrées, zéro
écart de champ, sauvegardes présentes.

#### `--migrate-glossary` — réintégrer un glossaire antérieur

La migration automatique n'a **qu'un déclencheur** : `glossary.load` sur le fichier canonique
`sources/<Projet>/glossaire.yaml`. Un ancien glossaire rangé ailleurs — un `glossaire.bak.yaml`,
un export, une copie d'une installation précédente, le glossaire d'une œuvre sœur — n'est lu par
personne, donc jamais converti. Si le fichier canonique a été régénéré entre-temps (par
`--extract-glossary` sur un tome, par exemple), le travail accumulé reste intact sur le disque
mais devient invisible pour l'application, et rien ne le signale.

```bash
python run.py "Mon LN" --migrate-glossary sources/Mon LN/glossaire.bak.yaml
python run.py "Mon LN" --migrate-glossary ancien.yaml oeuvre-soeur.yaml --remplacer
```

Les fichiers donnés **font autorité**, dans l'ordre (le premier sert de base) ; le glossaire
actuel du projet est fusionné en dernier, donc sans rien écraser. `--remplacer` l'ignore — cas
de récupération, quand c'est lui qui est abîmé ; il part quand même en
`glossaire.yaml.avant-reintegration.bak`, jamais réécrit par une seconde exécution.

⚠ **Les fichiers réintégrés ne sont jamais modifiés.** La conversion se fait en mémoire
(`glossary_import.lire_glossaire_yaml`), là où `glossary.load` réécrit le fichier qu'il migre —
sur un `.bak`, ce serait détruire le filet qu'on est venu chercher.

La fusion est celle du terminologue, exposée en dict→dict (`glossary_build.fusionner_glossaire`,
même corps que `merge_notes`) : appariement par `nom`/`variantes`/`termes_source` normalisés,
union des listes, la base primant sur `nom`/`description`/`role`.

#### L'accord grammatical devient une fonction du pack

`core/glossary_force.py` était français dans son fond : `_DET_FEM`, `_DET_MASC`, l'élision, et
le `h` exclu parce que muet ou aspiré est indécidable sans dictionnaire. Ces règles sont
désormais `AccordFrancais` ; `AccordNeutre` sert les langues sans accord. Un pack le déclare
par `accord: francais|aucun`, et le défaut reste le français.

⚠ « Ne rien faire » est une réponse **complète**, pas une implémentation en attente : l'anglais
n'a ni genre, ni élision, ni déterminant à réécrire, donc le forçage s'y réduit à la
substitution. Le principe est préservé et testé des deux côtés — **le déterministe ne doit
jamais introduire une faute que le modèle n'aurait pas faite**.

#### Pack anglais

`langues/en/` : les huit prompts, le guide de style et la typographie, **adaptés et non
traduits**. Le cas le plus net est l'incise d'attribution — le français inverse et met le verbe
en tête (« dit-il »), l'anglais commence par le sujet (`she said`) — suivi du temps du récit,
l'anglais n'ayant pas de passé littéraire séparé, et des honorifiques, que la fan-traduction
anglophone conserve là où l'usage français les supprime.

Le parseur de glossaire (`core/glossary_build.py`) accepte désormais les mots-clés anglais en
entrée — `### CHARACTERS`, `gender:`, `variants:` — ramenés au schéma français. Sans cela, le
glossaire d'un tome traduit vers l'anglais serait ressorti vide sans qu'aucun compteur ne s'en
aperçoive.


### Langue cible configurable et packs de langue

Le projet acceptait cinq langues **sources** et ne produisait que du **français**. Pas par
choix d'architecture : la langue de sortie n'était écrite nulle part en particulier, elle
était partout. Elle vit désormais dans un **pack**, `langues/<code>/`, et ajouter une langue
devient un dossier de données à contribuer — sans toucher au moteur.

```yaml
langues:
  cible: fr        # le pack de sortie
  packs: langues   # où les chercher
```

**Aucune rupture.** Une config qui ne mentionne ni `langues.cible` ni `langues.packs`, sur une
installation sans dossier `langues/`, lit ses prompts, son guide de style et ses gabarits là
où elle les a toujours lus. Vérifié : `--dry-run` sur un tome de 61 chapitres rend les 64
fichiers Markdown identiques au bit près, hors les deux lignes d'horodatage qui diffèrent déjà
entre deux runs du même code.

#### ⚠ Les prompts ont DÉMÉNAGÉ (aucun n'a été réécrit)

`prompts/` → `langues/fr/prompts/`, `style_guide.md` → `langues/fr/style_guide.md`,
`templates/{reference.docx,epub.css}` → `langues/fr/templates/`.

Les huit fichiers — `traducteur.md`, `correcteur.md`, `terminologue.md`, `glossariste.md`,
`mise_en_page.md`, `manga_traducteur.md`, `manga_contexte.md`, `manga_onomatopees.md` — sont
déplacés **sans qu'une ligne change** (git les enregistre en `rename (100%)`). La voix de la
traduction est donc strictement inchangée.

Conséquence sur la règle de numérotation, qui cite `git checkout v0.9.0 -- prompts/` :
reproduire la voix d'un tome antérieur à cette version se fait toujours ainsi, mais reproduire
celle d'un tome POSTÉRIEUR demande `git checkout <tag> -- langues/fr/prompts/`.

#### Ce qui a été externalisé

- **Typographie** (`langues/fr/pack.yaml`) : guillemets, tiret de dialogue, ponctuation de fin
  de phrase, titre du guide de style, styles Word et classes CSS.
- **Les verbes de parole.** `pipeline/render.py` portait ~40 verbes français conjugués, forme
  inversée comprise, pour décider si une incise reste collée à sa réplique. Ce n'est pas un
  caractère à paramétrer mais une CONSTRUCTION de langue, que l'anglais n'a pas (`"...," he
  said`, sans inversion). Un pack peut donc déclarer qu'il n'en a pas, et le rendu n'essaie
  alors pas de coller d'incise — plutôt que de le faire selon des règles françaises.
- **Six consignes construites en dur en Python**, que l'inventaire a révélées : les quatre
  paliers de naturalisation, la traduction des titres de chapitre, la ligne de romanisation du
  terminologue et la consigne de traduction unitaire manga. Sans elles, un pack complet aurait
  encore produit du français sur quatre chemins.

Le texte français de ces six consignes **reste à son site d'appel** dans le code, le pack ne
faisant que le surcharger. Le recopier dans le pack `fr` en aurait fait une seconde source,
libre de diverger, dont l'une décide de la sortie d'un tome.

#### Aucun repli silencieux

Un pack introuvable ou incomplet arrête le run **au démarrage**, avec la liste des packs
disponibles et une suggestion de faute de frappe. Six heures de GPU pour découvrir qu'un tome
est sorti dans la mauvaise langue coûtent bien plus cher qu'un refus immédiat. Les huit
prompts sont exigés au complet ; les gabarits `docx`/`css` sont facultatifs, un
`reference.docx` étant déjà un réglage que l'utilisateur cale sur son propre document.

`rendu.reference_docx`, `rendu.epub_css` et `chemins.style_guide` passent à `null` dans
`config.yaml` : vides, ils prennent la valeur du pack. **Renseignés, ils PRIMENT** — c'est
ainsi qu'on impose ses propres gabarits, et c'est ce qui fait qu'un chemin fautif est signalé
par `--check` au lieu d'être masqué par celui du pack.

#### Ce qui n'est pas encore fait

Le **glossaire** reste français dans son schéma (`nom`, `pluriel`, `genre`) et dans son forçage
déterministe (`core/glossary_force.py` accorde les déterminants et répare les élisions). Le
rendre multi-cibles réécrit tout `glossaire.yaml` existant : c'est un **MAJEUR**, prévu pour la
2.0.0. Un pack non français fonctionne dès maintenant, mais ses accords de glossaire resteront
français — limite connue, documentée dans
[`docs/mesures/inventaire-couplage-fr.md`](docs/mesures/inventaire-couplage-fr.md) et
[`langues/README.md`](langues/README.md).


**Le détecteur voyait les webtoons à 6 % de leur taille.** `_letterbox` met toute la planche
dans un carré 640×640 en conservant le ratio. Sur une bande de 1080×10000, elle devient
**69×640 — 10,8 % de la largeur du canevas**, le reste étant du gris, et une bulle de 400×500 px
arrive au réseau en **27×34 px**, soit ~3×4 cellules au stride 8 de YOLOv8.

Ce n'était pas une affaire de seuil, contrairement à l'intuition : mesuré sur
*webtoon A* Chap.11, descendre `conf_threshold` jusqu'à **0,10 ne récupère AUCUNE
bulle** sur quatre planches. Le réseau ne les émettait pas du tout.

La détection découpe désormais les bandes très allongées en fenêtres pleine largeur de 2160 px
(2× la largeur), avec 900 px de recouvrement. La même bulle arrive alors en 118×148 px.

| planche | avant | après | score médian |
|---|---|---|---|
| 2 | 6 bulles | **7** | 0,90 → 0,94 |
| 4 | 10 bulles | **11** | 0,90 → 0,93 |
| 8 | 4 bulles | **7** | 0,90 → 0,94 |

⚠ **Le recouvrement doit rester ≥ la plus haute bulle attendue** (833 px sur le corpus) : c'est
l'invariant qui garantit que toute bulle est entièrement contenue dans au moins une fenêtre, et
donc qu'écarter les détections coupées par une couture ne perd rien. Une bulle plus haute que le
recouvrement n'est jamais jetée pour autant — elle reste candidate en second rang, tronquée,
parce qu'une bulle tronquée se retaille dans l'éditeur alors qu'une bulle absente ne se voit pas.

Le découpage se déclenche sur le **ratio mesuré** (`hauteur/largeur > 3`) et non sur le format :
une planche manga paginée (1440×2048, ratio 1,4) occupe déjà 70 % du canevas et garde son chemin
au bit près. Réglages : `manga.detection.fenetre_hauteur`, `fenetre_recouvrement`,
`fenetre_ratio_min`, surchargeables par format.

⚠ **Coût assumé** : une inférence par fenêtre, soit 8 pour une planche de 10 000 px. La
détection passe de ~8 s à ~70 s par planche. Il ne concerne que les formats allongés.

### Un visage de personnage avait été repeint couleur peau

Planche 4 : fausse détection sur un visage (score 0,569, OCR vide), et **45,6 %** d'une zone de
488×619 px repeinte en `[252, 215, 175]` — la couleur de peau, échantillonnée dans ses propres
pixels. Deux autres fausses bulles avaient subi le même sort.

La cause est une logique **monotone dans le mauvais sens** dans `manga/clean.py` : plus une zone
est uniforme, plus le nettoyeur est confiant qu'il peut la repeindre — alors qu'une zone plate
est justement une zone *sans texte*. Le seul garde-fou existant (`seuil_abandon`) n'attrapait que
les zones **texturées**, c'est-à-dire le cas exactement opposé.

**Aucune statistique de pixels ne sépare une fausse bulle d'une vraie**, et c'est mesuré, pas
supposé. Un véto préventif fondé sur la densité d'encre a été essayé puis **rejeté** :

| | densité d'encre | saturation du fond |
|---|---|---|
| Vraies bulles (26) | 0,030 → 0,545 | 0,000 → **0,355** (bulle rose) |
| Faux positifs (3) | **0,164 / 0,212 / 0,279** | 0,000 / **0,306** / 0,020 |

Les intervalles se chevauchent dans les deux sens : un dessin est plein de contrastes, et une
bulle peut être légitimement colorée.

Le seul séparateur fiable est le **texte** — et il n'existe pas encore au nettoyage, `nettoyage`
et `ocr` étant des frères indépendants dans le graphe de cache. D'où une réparation au **RENDU**
(`rendu.restaurer_sans_texte`), où tout est connu : une région qui n'a **ni source OCR ni
réplique** voit ses pixels d'origine recollés avant le lettrage. La double condition compte —
restaurer une bulle dont l'OCR a échoué mais qu'on a corrigée à la main dessinerait le texte
d'origine sous la traduction française.

Corollaire appréciable : un simple `--from rendu` répare une planche, **sans un seul appel LLM**.
Les zones restaurées sont listées dans `RAPPORT.md` — ce sont des fausses détections probables,
et c'est actionnable.

Vérifié sur la planche 4 : la zone du visage est redevenue **identique au pixel près** à la
source (34 154 couleurs contre 16 122 après dégât).

### Deux bulles proches s'amputaient mutuellement

`checkpoints.save_regions` écrit une image d'**étiquettes** : un pixel partagé va à la dernière
bulle écrite, et le masque de l'autre revient amputé au rechargement — en silence et
définitivement. Mesuré sur la planche 3 : deux bulles se recouvraient sur **36 108 px**. Selon le
chemin, cela écrasait les glyphes d'une bulle par ceux de sa voisine (run frais, masques encore
chevauchants en mémoire) ou rognait son texte (reprise, masques relus amputés).

`document.rendre_disjoints` corrigeait déjà exactement cela — mais n'était câblée que sur
l'éditeur, jamais sur le pipeline. Elle l'est désormais, les régions étant triées par **score
décroissant** au préalable : la bulle la mieux notée garde ses pixels. Le rapport et le journal
listent les bulles rognées.


**L'éditeur graphique cesse d'écrire par deux voies concurrentes.** Ajouter une bulle au
milieu d'une planche décalait les répliques suivantes, affichait « … » sur des bulles
pourtant traduites, et finissait par lever à l'enregistrement :

```
manga.document.ErreurDocument: bulle 6 inconnue : la planche en compte 6
```

Un seul défaut derrière les trois. `manga/edition.py` écrit sur le **disque** depuis le fil de
travail, en passant par `document.poser_regions` — qui fait correctement son travail : il
retrie par ordre de lecture et remappe `ocr`, `traduction`, `manuelles`, `origines` et
`mises_en_page` par appariement IoU. Mais l'éditeur garde en parallèle un `DocumentPlanche`
**en mémoire**, qui n'était jamais invalidé. Après un ajout, le disque avait 7 régions
correctement remappées, la mémoire 6 d'avant l'insertion — et `_appliquer_document` réécrasait
les bulles fraîches avec les textes périmés, **par position**.

### Le sens de lecture, oublié sur le chemin d'édition

Plus grave, et invisible : `document.poser_regions` appelait `reading_order()` **sans le sens
de lecture**, donc toujours droite→gauche. Sur un webtoon, la moindre édition de zone re-triait
donc toute la planche en ordre manga. Le défaut était silencieux à trois titres — le nombre de
bulles restait juste, `regions.json` continuait d'annoncer le bon sens (`save_regions` préserve
le champ), et les textes avaient bien suivi leurs bulles : c'est l'**ordre des bulles entre
elles** qui était faux.

`EtatPlanche` porte désormais un champ `sens`, rempli par `lire_etat` depuis
`checkpoints.sens_enregistre` et consommé par `poser_regions`. C'est le point d'insertion le
moins invasif : aucun appelant ne change de signature.

**Nouvel outil — `tools/verifier_ordre.py`.** Contrôle en lecture seule que l'ordre persisté
suit le sens déclaré, et `--corriger` le remet en place par **permutation seule** : rien n'est
re-détecté, re-lu ni retraduit, et les bulles ajoutées à la main sont conservées. Conseiller
`--from detection` à la place aurait jeté précisément le travail qu'on cherche à sauver. Une
planche dont les bulles sont empilées verticalement sort identique dans les deux sens : l'outil
la déclare « indifférente au sens » plutôt que saine, pour ne pas laisser croire à un contrôle
plus fort qu'il n'est.

### Une seule voie d'écriture

- `PanneauEditeur.invalider_document(numero)`, appelée par `fenetre._sur_fin` après toute tâche
  `GENRE_EDITION` réussie : le disque fait foi, le document est relu.
- **Filet défensif** dans `_charger_planche` : un document dont le nombre de régions ne
  correspond plus au disque est relu au lieu d'être appliqué. C'est la garde qui manquait, et
  elle couvre les chemins d'écriture qu'on oublierait de brancher plus tard.
- Le document est **vidé sur disque avant** l'édition : `poser_regions` remappe les corrections
  qu'il trouve dans le cache, pas celles restées en mémoire.
- Corrige du même coup la suppression, la scission, le redessin et la retaille, qui souffraient
  du même défaut — en **échec silencieux** pour eux : pas de crash, mais les textes périmés
  réécrits par-dessus les bonnes régions au premier enregistrement.

### Les brouillons suivent leur bulle

Une insertion décale les index ; une réplique tapée mais non retenue doit suivre **sa** bulle.
Nouveau `geometry.suivre_boites`, qui généralise à un lot ce que `_resuivre_zone` faisait déjà
pour une seule zone, au même seuil (`edition.SEUIL_REPORT`) et par appariement glouton — sans
lui, deux anciennes boîtes proches réclameraient la même nouvelle. Un brouillon dont la bulle a
disparu est abandonné **avec un message** : le reposer au jugé écrirait une réplique dans la
mauvaise bulle, ce qui est pire que de la perdre — une perte se voit, un déplacement silencieux
se découvre au rendu final.

### Le zoom ne saute plus

`_reprendre_cadrage` retombait sur `fitInView` sauf si le bouton 🔒 était coché. Or celui-ci
répond à « garder le cadrage en **changeant** de planche ? », qui est une autre question :
quand on recharge la planche qu'on est déjà en train de regarder, reperdre son zoom n'est
jamais ce qu'on veut. Sur un webtoon de 9 551 px de haut, chaque bulle ajoutée ramenait la
planche à 3 %. Le cadrage est désormais restauré inconditionnellement sur un rechargement de la
**même** planche ; le 🔒 garde son sens pour la navigation.

### Le gel pendant l'édition

L'écriture, les masques et la repeinte étaient déjà dans la file de fond. Ce qui gelait :

- **`_masque_etire`** appelait `load_regions` — décodage de `masks.png` **pleine page** et
  reconstruction des masques numpy de toutes les bulles — pour **jeter le résultat** la ligne
  suivante, puisqu'un document existe toujours. Et il est appelé à **chaque événement de
  mouvement de souris** pendant qu'on tire une poignée. Les deux lignes sont inversées.
- **`_contexte()`** résolvait l'image source sur le fil d'affichage, ce qui peut **extraire une
  archive CBZ entière** — dans le gestionnaire de relâchement souris. Nouveau
  `_fabrique_contexte()` : tout ce qui est bon marché est capturé tout de suite, la résolution
  de la source est repoussée dans la file.
- **Le fond de planche** était redécodé à chaque rechargement. Cache par `(chemin, mtime)` dans
  `scene_planche` — le mtime change quand `repeindre_clean` passe, donc le cache se rafraîchit
  quand il le faut ; deux entrées seulement, un `QPixmap` de webtoon pesant plusieurs dizaines
  de Mo.

### `QThread: Destroyed while thread is still running`

`closeEvent` attendait 2 s / 3 s ; au-delà, Qt détruisait l'objet `QThread` C++ pendant que le
fil tournait encore. L'attente est désormais bornée par tranches (5 s pour les aperçus, 30 s
pour les travaux) et, si un fil ne rend toujours pas la main, on le **dit** au lieu de fermer en
silence — une tâche coupée en plein `save_regions` laisse un checkpoint incomplet, et c'est
exactement ce que l'utilisateur doit savoir. On ne tue toujours pas le fil : la sentinelle
reste le seul mécanisme d'arrêt.


**La brique manga apprend la langue source et le format de planche.** Elle supposait le
japonais partout, sans jamais le dire. Sur un webtoon **anglais** (*webtoon A*
Chap.11), `manga-ocr` — un ViT+BERT entraîné sur du japonais vertical, dont le décodeur n'a
pas de token d'espace — a rendu :

| Vérité terrain | Lu par `manga-ocr` | Traduit en |
|---|---|---|
| `I'LL BE TAKING YOUR LIFE` | `２０１６年１０月１９日に２０日` — kanji **inventés** | « 19 octobre 2016, le 20 » |
| `HE'S CERTAINLY NO ORDINARY PERSON` | `ＨＥＳＣＥＲＴＡＮＡＹＮＯＯＯＲＤＩＮＡＲＹＰＥＲＳＯＮ` | recopié tel quel |

Le modèle de traduction n'a jamais vu d'anglais : il a traduit consciencieusement cette
bouillie. Tout le reste du rapport en découlait — 2 planches en échec `japonais_residuel` (les
`の` hallucinés déclenchaient le garde-fou), 5 relances brûlées, 12 traductions vides,
15 glyphes supprimés au rendu, 0 entrée de terminologie sur 9 planches. **Rien, dans le
rapport, ne disait que la chaîne attendait du japonais.**

### La langue source se déclare, comme pour le light novel

```
sources/<Projet>/<Tome>/<FORMAT>/<LANGUE>/*.png|cbz
```

Les deux niveaux sont **facultatifs**, avec repli en cascade — aucun tome existant ne change
de comportement :

| Sur disque | format | langue |
|---|---|---|
| `<Tome>/manga/*.png` (structure historique) | `manga` | `manga.langue_source` (`jp`) |
| `<Tome>/*.png` (repli historique) | `manga` | `manga.langue_source` |
| `<Tome>/manga/ENG/*.png` | `manga` | `en` — lecture **droite→gauche** |
| `<Tome>/webtoon/ENG/*.png` | `webtoon` | `en` — lecture **gauche→droite** |

La table des noms de dossiers est celle du light novel (`langues.dossiers`), et
`scan/pages.py` fournissait déjà le patron de scan. Nouveaux flags : `--langue DOSSIER` et
`--format {manga,webtoon}`. Nouvelles clés : `manga.langue_source`, `manga.ocr.moteur`,
`manga.formats.*`.

`manga/sources_manga.py:resoudre_source` devient le point d'entrée **unique** de cette
résolution : `manga/serie.py` (pré-vol) et `gui/modele_tome.py` en avaient chacun une copie,
et trois copies d'une règle à quatre branches auraient fini par désigner trois chapitres
différents.

### Un OCR par langue

`manga/ocr_routeur.py` route sur la langue : `manga-ocr` pour le japonais — il y est
imbattable et rien ne change pour lui —, **RapidOCR / PP-OCRv4** (`manga/ocr_latin.py`) pour
le latin, le cyrillique et le hangûl. Les deux exposent la même surface (`read`, `read_all`).
Sur la planche citée, les 10 bulles ressortent correctement, et l'OCR passe de 41 s à 2,3 s
par planche.

Nouvelle dépendance **optionnelle** : `rapidocr-onnxruntime` (cf. `requirements-manga.txt`).
Elle n'est importée que si la source n'est pas japonaise, et son absence produit un message
qui dit quoi installer. ⚠ Limite mesurée et assumée : son détecteur rate parfois une bulle de
ponctuation seule (`...`). Le repli évident — relancer la reconnaissance sur le crop entier —
a été essayé et **rejeté** : il rend `福` sur la bulle en question, c'est-à-dire qu'il invente.

### Le format `webtoon`, et le sens de lecture qui suivait le mauvais axe

`manga.rendu.sens_lecture` n'alimentait que la métadonnée `ComicInfo.xml` — **jamais** la
numérotation des bulles envoyée au modèle, câblée droite→gauche dans `ocr.reading_order`. Sur
un webtoon, deux bulles côte à côte partaient donc numérotées à l'envers, sans aucune alerte
puisque leur *nombre* restait juste.

⚠ Le sens de lecture est une propriété du **format**, jamais de la langue : un scan anglais
d'un manga japonais se lit droite→gauche, un webtoon coréen se lit gauche→droite. D'où un axe
`format` distinct, et une surcouche de config qui **redéclare seulement ce qui diffère** —
le webtoon tient en trois lignes de `config.yaml` et hérite de tout le reste.

**Aucun incrément de `checkpoints.FORMAT_VERSION`** : il ferait retraduire *tous* les projets
existants. Le sens est enregistré dans `regions.json` (champ ignoré par un lecteur ancien), et
seules les planches dont le sens a réellement changé sont reprises.

### Les garde-fous et les consignes ne parlent plus japonais

- `quality_manga` — `japonais_residuel` devient un motif générique. Sur une source CJK, la
  détection par charset est inchangée ; sur une source latine, aucune classe de caractères ne
  peut trancher (l'anglais et le français partagent l'alphabet), donc on repère la **recopie à
  l'identique**. La clé du motif reste `japonais_residuel` — elle est persistée dans les
  `qa.json` déjà écrits —, seul le libellé nomme la vraie langue.
- `text_detection.trier_zone` — l'heuristique **s'inverse** avec la langue. Sur une source
  japonaise, du latin signale une hallucination de `manga-ocr` et part au rebut ; appliquer
  cette règle à une source anglaise jetait **toutes** les onomatopées de l'œuvre en silence.
- Les consignes de langue vont dans le **message**, pas dans les prompts — ceux-ci sont
  partagés entre œuvres et avec le light novel. Même précédent que
  `glossary_lang.consigne_pivot_cjk()`. `prompts/manga_traducteur.md`,
  `manga_onomatopees.md` et `manga_contexte.md` deviennent neutres et parlent de « bande
  dessinée » ; `manga_onomatopees.md` gagne des exemples latins.
- `RAPPORT.md` annonce désormais format, langue source et sens de lecture **en tête**.

### Un manga déjà en langue cible

Un tome dont la source est déjà du français porte `mode: "glossaire"` et un run complet
s'arrête net en renvoyant vers `--extract-glossary`, plutôt que de basculer en silence. Le
mode `glossaire_seul` faisait déjà exactement « relever sans traduire » : il ne lui manquait
que l'OCR latin et un en-tête de terminologue honnête (il annonçait « bulles en JAPONAIS »).


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
