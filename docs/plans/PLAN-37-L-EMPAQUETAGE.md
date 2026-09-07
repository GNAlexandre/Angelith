# PLAN 37 — L'empaquetage : `pyproject.toml`, un dossier gelé, un installeur, un artefact de CI

> **Lire `00-CONTEXTE-AGENT.md`, puis `README-INTERFACE-31-37.md`.**
>
> **Nature attendue** — **MINEUR pour le dépôt, MAJEUR pour l'installation.** Le code livré ne
> change pas de comportement pour qui lance `python gui.py` ; mais L37.4 déplace `config.yaml`
> et `.angelith/` **dans une installation gelée**, et c'est exactement la définition de MAJEUR du
> dépôt (« l'utilisateur doit supprimer `build/` ou éditer `config.yaml` »). ⚠ **Tranchez le
> numéro à la livraison**, d'après ce que le lot fait réellement à l'utilisateur du dépôt — pas à
> celui de l'installeur, qui n'existait pas avant.
>
> **Charge estimée** — 14 jours, dont 3 pour la seule étape 0 (peser) et 3 pour l'installeur et
> la question de la signature.
>
> **Prérequis : `PLAN-31` et `PLAN-36`.** Un `.exe` qui ouvre un tome au hasard au démarrage et
> qui ne sait pas se diagnostiquer est un `.exe` qu'on ne peut pas donner à quelqu'un.
>
> ⚠ **Se lance sur le PC PRINCIPAL** — il installe, il gèle, il pèse, il signe.

---

## 1. L'état, relevé à la source le 2026-09-04 (2.24.1, `8e5ee5a`)

### 1.1 Rien n'est empaqueté, et c'était un choix documenté

- **aucun `pyproject.toml`**, aucun `setup.py`, aucun fichier `.spec`. Vérifié.
- **cinq** `requirements-*.txt` : socle, `-gui`, `-manga`, `-scan`, `-dev`.
- lancement par `python run.py` / `run_manga.py` / `run_ocr.py` / `run_illustration.py` /
  `app.py` / `gui.py`.
- version : **`core/version.py` est la source unique**, et `tests/test_version.py` la compare à
  la première entrée datée du `CHANGELOG.md`.

⚠ **La docstring de `core/version.py` justifie l'absence de `pyproject.toml`** : « Pas de
`pyproject.toml` : le projet n'est pas empaqueté, il se lance par `python run.py`. Un littéral
Python évite donc une lecture disque relative à `__file__` (fichier VERSION) ou un parseur TOML
au démarrage. »

**Ce lot rend cette phrase fausse, donc il doit la LEVER dans le fichier**, dans la forme
prescrite par la règle §5 bis du contexte agent : un bloc daté qui lève l'affirmation
précédente, plutôt qu'une réécriture qui effacerait l'histoire. Le précédent est dans le même
fichier (« ⚠ MISE À JOUR 2.16.0 : la première réserve est LEVÉE »).

⚠ **Et l'argument technique de la docstring reste valable** : le littéral Python reste la source
unique. `pyproject.toml` doit lire `__version__` **dynamiquement**
(`[tool.setuptools.dynamic] version = {attr = "core.version.__version__"}`), jamais le
recopier. Deux numéros de version, c'est un `tests/test_version.py` qui passe pendant qu'on
livre le mauvais numéro.

### 1.2 Ce qu'il faudrait geler, et le problème est là

| Ce qui doit partir | Taille connue | Remarque |
|---|---:|---|
| le code du dépôt | ~quelques Mo | — |
| `config.yaml` | **158 493 o** | ⚠ c'est un **document** de prose commentée, pas un fichier de réglages |
| `templates/` (dont `reference.docx`) | — | contrat de styles Word, vérifié par des tests |
| `langues/` (les prompts) | — | ⚠ « les prompts sont du code source » (interdit 6) |
| PySide6 | plusieurs centaines de Mo | Qt entier, à élaguer par plugins |
| `onnxruntime`, `numpy`, `pymupdf` | — | binaires natifs, hooks PyInstaller à vérifier |
| **`torch` + `transformers`** (via `manga-ocr`) | ⚠ **plusieurs Go, à mesurer** | c'est **la** question de ce lot |
| poids ONNX, modèle `manga-ocr` | — | ⚠ **non redistribuables ou à licence à vérifier** — ne partent PAS |

⚠ **Un `.exe` qui embarque `torch` n'est pas un téléchargement, c'est une distribution
logicielle.** Et il embarquerait une pile d'apprentissage profond entière pour **un** usage :
l'OCR japonais, dont le dépôt a par ailleurs mesuré la faiblesse hors bulle
(`docs/mesures/sfx-2026-08-28.md` : exact 6 fois sur 41). C'est la décision de l'étape 0.2, et
elle décide de la forme du produit.

### 1.3 Ce que la CI sait déjà faire

`.github/workflows/ci.yml` : deux jobs, **tous deux `windows-latest`**, Python 3.12 —
`ruff check .` puis `pytest -m "not lent and not modeles" -q`, puis un banc de détection sur le
corpus synthétique. `QT_QPA_PLATFORM: offscreen`.

⚠ **`windows-latest` n'est pas une préférence, c'est un contrat** : `tests/conftest.py` fabrique
sa planche synthétique avec `C:/Windows/Fonts/msgothic.ttc` et **skippe** si la police manque —
sur un runner Linux, toute la couverture détection/OCR/orchestrateur serait sautée en silence.
Rendre la police configurable est un prérequis de toute matrice d'OS, et c'est le `PLAN-20`.

Et il existe déjà des outils de livraison : `tools/notes_de_version.py`,
`tools/verifier_livraison.py`, `tools/verifier_disclosure.py`, `tools/compte_de_tests.py`.

### 1.4 Les normes d'empaquetage, telles qu'elles se lisent aujourd'hui

- **onedir plutôt que onefile.** Le mode un-fichier **extrait au démarrage** dans un dossier
  temporaire, et « ce motif extraction-puis-exécution est exactement ce que fait beaucoup de vrai
  logiciel malveillant » : c'est ce qui déclenche les heuristiques antivirus. Le mode un-dossier
  ne l'a pas. Pour un paquet de plusieurs centaines de Mo, il évite en plus une extraction à
  chaque lancement.
- **la signature de code réduit fortement** les faux positifs Defender et les avertissements
  SmartScreen ; un certificat EV davantage encore. Sans signature, un `.exe` neuf **déclenche**
  SmartScreen — c'est le comportement normal, à annoncer plutôt qu'à découvrir.
- **recompiler le chargeur PyInstaller** localement change l'empreinte du binaire partagé qui a
  été signalé chez les éditeurs — remède connu, à mesurer et non à supposer.
- **les éditeurs acceptent les signalements de faux positif**, mais chaque reconstruction doit
  être resoumise, sauf si c'est le **certificat** qui est mis en liste blanche.
- **Nuitka** compile vers du natif au lieu d'empaqueter un interpréteur, ce qui passe mieux les
  heuristiques — au prix d'une chaîne de compilation.

---

## 2. Étape 0 — peser, puis décider de la forme du produit

### 0.1 — Le poids réel, par jeu de dépendances

Dans quatre venv **propres**, sur le PC principal, installez et pesez :

| Jeu | Contenu | Taille du venv | Taille gelée (onedir) |
|---|---|---:|---:|
| A — socle + GUI | `requirements.txt` + `requirements-gui.txt` | | |
| B — A + manga **sans** `manga-ocr` | + `numpy`, `onnxruntime`, `rapidocr-onnxruntime`, `rarfile` | | |
| C — B + `manga-ocr` | donc + `torch`, `transformers` | | |
| D — C + scan | `requirements-scan.txt` | | |

Publiez aussi, pour chacun : le temps de démarrage de l'exécutable gelé jusqu'à la première
fenêtre, et le nombre de fichiers du dossier.

⚠ **Ne citez aucune taille de mémoire.** Les tailles annoncées par les pages de projet ne sont
pas des mesures de ce que produit *cette* chaîne sur *cette* machine, et la règle des chiffres du
dépôt s'applique : « un chiffre sans dénominateur n'est pas une mesure, c'est une impression ».

### 0.2 — La décision qui découle, et il y en a trois candidates

D'après le tableau, tranchez **par écrit** :

| Forme | Ce qu'elle donne | Ce qu'elle coûte |
|---|---|---|
| **un seul paquet, tout dedans** | une installation, tout marche | le poids du jeu D, y compris `torch`, pour un usage |
| **un paquet de base + OCR japonais récupéré après** | paquet du jeu B, léger ; `manga-ocr` installé par le diagnostic (`PLAN-36` L36.2) | ⚠ demande un Python **dans** le paquet capable d'installer — non trivial sur un gel |
| **un paquet de base + une extension téléchargeable préparée** | idem, sans `pip` chez l'utilisateur | il faut construire et héberger l'extension, et la versionner avec l'application |

⚠ **La deuxième option est un piège classique.** Un exécutable PyInstaller n'a pas de `pip`
utilisable ; « il suffira d'installer le paquet après » est une phrase qui ne survit pas à
l'essai. **Essayez-la avant de la choisir**, et publiez ce qui se passe.

⚠ **Et la question honnête est peut-être en amont** : la brique manga a-t-elle besoin de
`manga-ocr` pour être utile ? Le dépôt a `rapidocr-onnxruntime` pour le latin, et un
`ocr_routeur`. Un paquet qui traduit **les sources latines** (le webtoon anglais du corpus) sans
`torch` est un produit livrable ; ce serait un périmètre annoncé, pas une amputation cachée.
Mesurez-le : combien des 17 œuvres sont exploitables sans OCR japonais ?

### 0.3 — Ce que l'installation ne contient pas, écrit avant de commencer

La liste, en clair, qui devient le texte de l'installeur **et** de la page de téléchargement :

- **aucun poids de détection** — le détecteur en place est GPL-3.0 + Manga109-s : non
  redistribuable (`PLAN-36` §1.3) ;
- **aucun modèle de langue** — Ollama et ses modèles s'installent séparément ;
- **aucun modèle d'OCR** — récupéré depuis sa source, avec consentement ;
- **ni Pandoc, ni WeasyPrint, ni `unrar`, ni ComfyUI** ;
- **aucune œuvre**, évidemment ; le tome de démonstration du `PLAN-36` L36.4 est synthétique.

⚠ **C'est cette liste qui décide si l'empaquetage tient sa promesse.** Un « installeur en un
clic » qui laisse cinq installations manuelles à faire doit le dire à l'écran 1, pas à l'écran 6.

---

## L37.1 — `pyproject.toml`, et la version reste unique

Un `pyproject.toml` qui :

- déclare le projet sous le nom public **Angelith** (cf. `PLAN-36` L36.5 : la question du nom est
  tranchée dans les faits depuis longtemps) et la licence **AGPL-3.0-or-later** ;
- lit la version **dynamiquement** depuis `core.version.__version__` — jamais un littéral
  recopié. `tests/test_version.py` gagne une assertion : la version lue par les métadonnées du
  paquet est celle de `core/version.py` ;
- déclare les points d'entrée en console **et** en fenêtre :
  `angelith`, `angelith-manga`, `angelith-ocr`, `angelith-illustration` (console) et
  `angelith-gui` (`gui_scripts`, pour ne pas ouvrir de console noire sous Windows) ;
- ⚠ **lève l'affirmation de `core/version.py`** dans le fichier lui-même, avec sa date, sans
  effacer l'ancienne.

## L37.2 — Les extras remplacent les cinq `.txt`, sans les casser tout de suite

`[project.optional-dependencies]` : `gui`, `manga`, `scan`, `illustration`, `dev`.

⚠ **Les cinq `requirements-*.txt` restent, et deviennent des enveloppes** (`-e .[manga]`) plutôt
que de disparaître. Motif : le critère 3 de la définition de « terminé » (« le comportement livré
par défaut est **iso** pour un utilisateur qui ne touche à rien »), et surtout la CI, les
documents et les procédures du dépôt qui les citent nommément. Les supprimer est un lot
ultérieur, avec sa migration.

⚠ **Le `.spec` de PyInstaller n'est pas la place des dépendances.** Un jour où l'un des deux
divergera, c'est le gel qui manquera un module — et le symptôme sera un `ImportError` chez
l'utilisateur, pas chez vous.

## L37.3 — PyInstaller, en **onedir**, et pourquoi

Un `angelith.spec` unique produisant un dossier, avec :

1. **les données** : `config.yaml`, `templates/`, `langues/`, les icônes de `gui/icones.py`.
   ⚠ Les prompts de `langues/` sont du **code source** (interdit 6) — ils doivent être dans le
   paquet, lisibles, et leur en-tête de licence reste **à la fin** du fichier ;
2. **les exclusions mesurées** : `pytest`, `tools/`, `tests/`, et les modules Qt inutilisés.
   Chaque exclusion se justifie par le tableau de poids de l'étape 0.1, pas par intuition —
   et **chaque exclusion se vérifie par un lancement**, parce qu'un module Qt retiré casse
   parfois un widget qu'on n'a pas ouvert au test ;
3. **les hooks à vérifier un par un** : `onnxruntime` (bibliothèques natives),
   `pymupdf`, `rapidocr-onnxruntime` (ses propres poids ONNX embarqués), `rarfile`,
   `weasyprint` s'il est dans le paquet ;
4. ⚠ **`--onefile` est refusé**, et le motif est écrit dans le `.spec` : l'extraction au
   démarrage déclenche les heuristiques antivirus et coûte une décompression à chaque
   lancement.

⚠ **Un `.exe` gelé n'a pas le même `sys.path` ni le même `__file__`.** Cherchez dans le dépôt
tous les chemins relatifs au fichier source — `templates/reference.docx`, `langues/<code>/`,
`manga_models/`, `.angelith/` — et faites-les passer par **une** fonction de résolution qui
connaît `sys._MEIPASS`. Un chemin oublié est une brique qui marche en développement et échoue
gelée ; c'est le mode de panne le plus courant de cet exercice.

## L37.4 — Où vivent `config.yaml` et `.angelith/` dans une installation

C'est le point MAJEUR de ce lot, et la contrainte est double : `config.yaml` est un **document**
de 158 Ko dont la prose est la documentation (interdit 5 — un aller-retour `yaml.safe_dump`
l'effacerait), et il ne doit **ni être réécrit, ni être perdu à la mise à jour**.

La résolution à livrer, dans cet ordre :

| Rang | Emplacement | Rôle |
|---|---|---|
| 1 | `--config <chemin>` | l'argument existe déjà partout, il gagne |
| 2 | la copie **utilisateur** (`%LOCALAPPDATA%\Angelith\config.yaml`) | modifiable par l'utilisateur, jamais écrasée par une mise à jour |
| 3 | la copie **livrée**, en lecture seule, dans le dossier d'installation | référence, et source de la copie au premier lancement |

Et `.angelith/` : la variable `ANGELITH_REGLAGES` **existe déjà** (`gui/reglages.py`), prévue
« pour les TESTS […] et pour une installation en lecture seule ». Elle est le mécanisme, il n'y a
rien à inventer — seulement à décider du défaut en mode gelé (le dossier utilisateur) et à le
tester.

⚠ **Trois pièges, chacun avec son test :**

1. le premier lancement **copie** le `config.yaml` livré s'il n'existe pas côté utilisateur, et
   **ne le remplace jamais** ensuite ;
2. une mise à jour du logiciel apporte un `config.yaml` livré plus récent, dont l'utilisateur
   ne bénéficiera pas. **Dites-le** : le diagnostic (`PLAN-36`) signale « votre `config.yaml`
   date de la version X, la version livrée est Y — voici ce qui a été ajouté ». Pas de fusion
   automatique : on ne fusionne pas un document ;
3. `chemins.sources` et `chemins.build` sont relatifs au dépôt aujourd'hui. Dans une
   installation, ils doivent pointer vers un dossier de **documents** de l'utilisateur, pas dans
   `Program Files`. C'est une valeur par défaut à décider et à écrire.

## L37.5 — L'installeur, et la vérité sur SmartScreen

Un script **Inno Setup**, et les décisions qui vont avec :

1. **installation par utilisateur** (`PrivilegesRequired=lowest`), pas dans `Program Files` :
   pas d'UAC, pas de dossier en lecture seule à contourner ;
2. **raccourci menu Démarrer** vers `angelith-gui.exe`, et un raccourci console optionnel ;
3. **désinstallation qui ne touche pas aux données** : ni `build/`, ni `sources/`, ni le
   `config.yaml` utilisateur, ni les poids téléchargés. Une case « supprimer aussi mes
   réglages », décochée ;
4. **la version vient de `core/version.py`** — l'installeur est généré, son numéro n'est pas
   saisi à la main ;
5. ⚠ **la signature.** Sans certificat, SmartScreen avertira sur chaque nouvelle version, et
   Defender peut signaler un faux positif. Ce lot doit :
   - **mesurer** ce qui se passe réellement : soumettez le binaire non signé à Defender à jour
     et à VirusTotal, publiez le taux (n moteurs sur m) **avec la date**, comme le dépôt le fait
     pour tout chiffre ;
   - **écrire la décision** : certificat acheté (avec son coût annuel), recompilation du
     chargeur PyInstaller mesurée, signalement de faux positif chez les éditeurs, ou **rien
     avec l'avertissement documenté** ;
   - ⚠ **et ne jamais chercher à contourner** une détection autrement que par la signature, le
     signalement ou un changement de chaîne d'empaquetage. Un contournement d'heuristique dans un
     logiciel libre est une ligne qu'on n'écrit pas.

⚠ **Nuitka reste une option ouverte, non retenue par défaut** : il produit des binaires que les
heuristiques signalent moins, au prix d'une chaîne de compilation dans la CI. Si l'étape 0.1
montre que PyInstaller ne tient pas (poids, temps de démarrage, faux positifs), c'est le repli —
mesuré, pas supposé.

## L37.6 — La mise à jour : rien, et c'est un choix

Ce lot **ne livre pas** de mise à jour automatique. Motif : un mécanisme de mise à jour est un
canal d'exécution de code sur la machine de l'utilisateur, et il demande une infrastructure
(signature, canal, rollback) qu'aucune mesure ne justifie aujourd'hui pour ce projet.

Ce qu'il livre à la place, et c'est optionnel :

- une **vérification de version** contre les releases GitHub, **désarmée par défaut**, sans
  télémétrie, sans identifiant, sans envoi de quoi que ce soit — un `GET` et une comparaison ;
- l'affichage « une version X est disponible » avec un lien, dans la page « À propos ».

⚠ **Désarmée par défaut** parce que le projet est « 100 % local, rien ne sort de la machine » et
que c'est l'un de ses six différenciateurs. Un appel réseau au démarrage, même anodin, contredit
la promesse — donc il est opt-in, et il le dit.

## L37.7 — La CI produit l'artefact, et le vérifie

Un job supplémentaire dans `.github/workflows/ci.yml`, sur `windows-latest`, déclenché sur les
tags :

1. **gèle** (`pyinstaller angelith.spec`), **construit l'installeur** (Inno Setup), publie les
   deux, avec l'empreinte **SHA-256** de chacun ;
2. **teste l'exécutable gelé** — et c'est le point qui donne sa valeur au job :
   - `angelith-gui.exe --version` rend la version de `core/version.py` ;
   - le **diagnostic structuré** du `PLAN-36` L36.1 tourne sur le binaire gelé et rend la liste
     de verdicts attendue pour une machine nue (aucun poids, pas d'Ollama, pas de Pandoc) — donc
     l'exécutable **sait dire ce qui lui manque** ;
   - la fenêtre s'ouvre sous `QT_QPA_PLATFORM=offscreen` et se ferme, sur l'accueil, **sans
     ouvrir de tome** (critère 2 du `PLAN-31`, vérifié une seconde fois sur le gel) ;
3. `tools/verifier_livraison.py` est étendu à ces artefacts, et `tools/notes_de_version.py`
   fournit le corps de la release.

⚠ **Un artefact non testé est un artefact qu'on livre cassé une fois sur trois** : les trois
tests ci-dessus attrapent exactement les trois pannes classiques du gel — la version perdue, un
chemin relatif à `__file__`, un module Qt élagué de trop.

## L37.8 — Linux et macOS : hors périmètre, avec le motif

- **macOS** est « out of scope » dans `docs/roadmap.md`, et le reste.
- **Linux** est bloqué par un prérequis nommé : `tests/conftest.py` dépend de
  `C:/Windows/Fonts/msgothic.ttc` et **skippe** si la police manque, donc une CI Linux passerait
  au vert sans tester la détection, l'OCR ni l'orchestrateur. Rendre la police configurable est
  l'étape L20.2 du `PLAN-20`, et c'est **le** prérequis d'un paquet Linux.

⚠ **Ne livrez pas un paquet Linux « parce que ça marche sur ma machine ».** Un paquet sans CI qui
l'exerce est une promesse que personne ne tient — et `docs/roadmap.md` liste déjà « One-click
Windows/Linux packaging » comme un jalon, ce qui rend la tentation réelle. Ce lot livre
**Windows**, et écrit ce qui manque pour Linux.

---

## 3. Les critères de ce lot

1. Le tableau de poids de l'étape 0.1 est publié pour les quatre jeux de dépendances : taille du
   venv, taille gelée, temps jusqu'à la première fenêtre, nombre de fichiers. Aucun chiffre repris
   d'une page amont.
2. La forme du produit est **tranchée par écrit** d'après ce tableau, y compris la réponse à
   « combien des 17 œuvres sont exploitables sans OCR japonais ». Si l'option « paquet + extension
   installée après » est écartée, l'essai qui l'écarte est publié.
3. `pyproject.toml` existe ; la version est lue **dynamiquement** depuis `core/version.py` ; un
   test compare la version des métadonnées du paquet à `__version__`.
4. L'affirmation « pas de `pyproject.toml` » de `core/version.py` est **levée par un bloc daté**,
   sans effacer l'ancienne (règle §5 bis).
5. Les cinq `requirements-*.txt` fonctionnent toujours ; `pip install -r` reste iso, ou le
   CHANGELOG dit précisément ce qui change.
6. Le gel est en **onedir**, le refus de `--onefile` est motivé dans le `.spec`, et chaque
   exclusion de module est justifiée par le tableau de poids **et** vérifiée par un lancement.
7. Une seule fonction résout les chemins de données (`sys._MEIPASS` compris) ; un test échoue si
   un chemin relatif à `__file__` subsiste pour `templates/`, `langues/`, `config.yaml` ou
   `.angelith/`.
8. Dans une installation gelée : `config.yaml` est résolu dans l'ordre CLI → utilisateur →
   livré ; il n'est **jamais** réécrit (test par empreinte SHA-256) ; il n'est jamais écrasé par
   une mise à jour ; l'écart de version avec le fichier livré est signalé par le diagnostic.
9. `chemins.sources` et `chemins.build` d'une installation ne pointent pas dans le dossier
   d'installation. La valeur par défaut est écrite et testée.
10. L'installeur s'installe **par utilisateur**, sans UAC, porte la version de `core/version.py`,
    et sa désinstallation ne supprime ni œuvres, ni `build/`, ni poids, ni `config.yaml`
    utilisateur par défaut.
11. Le comportement antivirus est **mesuré et publié avec sa date** (Defender à jour, et un taux
    n/m multi-moteurs), et la décision de signature est écrite : certificat, recompilation du
    chargeur, signalement, ou avertissement documenté. Aucun contournement d'heuristique.
12. Aucune vérification de version ne part sans opt-in explicite ; aucun identifiant, aucune
    télémétrie, aucun envoi.
13. La CI produit le dossier gelé et l'installeur avec leurs SHA-256, et **teste le gel** :
    `--version`, le diagnostic sur machine nue, et l'ouverture de la fenêtre sur l'accueil sans
    ouvrir de tome.
14. Le paquet Linux n'est pas livré, et le motif est écrit avec le nom de son prérequis
    (`PLAN-20` L20.2).
15. `ruff check .` passe ; `pytest -q -m "not modeles and not lent"` passe ; le compte de tests
    est publié **avec son dénominateur**.
16. `docs/mesures/empaquetage-<date>.md` reprend ces critères un par un, y compris les non
    tenus, et dit ce que la mesure ne dit pas.

## 4. Ce que ce lot ne fait pas

- Il ne redistribue **aucun** poids : ni détecteur, ni OCR, ni modèle de langue, ni poids
  d'illustration.
- Il n'installe ni Ollama, ni Pandoc, ni WeasyPrint, ni `unrar`, ni ComfyUI.
- Il ne livre **aucune** mise à jour automatique.
- Il n'envoie rien sur le réseau sans opt-in.
- Il ne livre pas de paquet Linux ni macOS.
- Il ne réécrit pas `config.yaml`, ne fusionne pas deux `config.yaml`, et ne convertit pas ses
  158 Ko de prose en réglages d'interface.
- Il ne change aucun comportement pour qui continue de lancer `python gui.py` depuis le dépôt —
  et un test le vérifie.
- Il ne contourne aucune détection antivirus autrement que par la signature, le signalement ou
  un changement documenté de chaîne d'empaquetage.
