# Créer un light novel, échanger un tome, se mettre à jour — mesure du 2026-09-06 (lot 40)

> **Machine** — PC principal, Windows 11 Pro 26200, Python 3.12.3.
> **Commit de départ** : `ae0df03` (2.33.0).
> **Empreinte SHA-256 de `config.yaml`** — convention : sur les octets **fins de ligne LF**,
> c'est-à-dire le fichier tel que git le stocke (le dépôt est en `core.autocrlf=true`, la copie
> de travail est donc en CRLF et n'a pas la même empreinte).
> `f61e9c864991…` avant, **`62da35fab412…`** après. Un seul changement de valeur :
> `maj.verifier` passe de `false` à **`true`**, sur décision du mainteneur, avec un bloc daté
> qui **lève** l'affirmation du lot 37 sans l'effacer (règle §5 bis).
> Aucun cache invalidé, `manga/checkpoints.py:FORMAT_VERSION` reste à **3**.

---

## 1. Étape 0 — les trois mesures demandées, et ce qu'elles ont changé

### 1.1 Le poids d'un `build/` complet contre celui de ses seuls checkpoints

Relevé sur **les 10 tomes manga du corpus**, soit **16,54 Go et 14 973 fichiers** au total.

| | poids | fichiers |
|---|---|---|
| dossier `build/<P>/<T>/manga/` complet | 16,54 Go (10 tomes) | 14 973 |
| dont `.checkpoints/` — **tout le travail humain** | **23 Mo, soit 0,1 %** | **10 852, soit 72 %** |
| dont `pages_psd/` | 65,1 % | — |

Un tome pèse de **0,7 à 3,3 Go** ; ses corrections, de **0,3 à 4,0 Mo**.

> **Ce que cette mesure décide** : la case « importer aussi les planches rendues » est
> **décochée** par défaut. Transférer 3 Go pour récupérer 4 Mo de corrections doit être un
> choix explicite, et le rapport 0,1 % / 72 % dit pourquoi les deux chiffres se contredisent —
> les checkpoints sont **nombreux et minuscules**, les rendus **rares et énormes**.

⚠ **Ce que la mesure ne dit pas** : elle porte sur des tomes de ce corpus, traités par ce
dépôt. Un tome dont les planches sources seraient déjà en PSD, ou dont la sortie serait en PNG
sans perte, déplacerait le rapport — pas dans un sens qui invalide la décision, mais le chiffre
lui-même n'est pas transposable.

### 1.2 L'aller-retour d'import sur une copie d'un tome réel

⚠ Interdit 7 du dépôt : jamais sur les vrais caches. L'aller-retour a donc porté sur des copies
et sur les arborescences synthétiques de `tests/test_import_build.py` (21 tests) — mêmes sept
fichiers suivis, même `projet.json`, même `FORMAT_VERSION`.

Ce que la mesure a trouvé, et qui a **changé l'implémentation** :

> `checkpoints.checkpoint_format` exige `regions.json` **et** `masks.png`. Elle répond à la
> question « puis-je charger ce cache ? », pas à « de quelle version est-il ? ». Un paquet reçu
> sans `masks.png` lui aurait donc fait rendre `None` — et le garde-fou de version aurait été
> **contourné en silence**.

C'est le refus qui compte le plus de tout le lot : l'ordre persisté dans `regions.json` est le
**pivot** auquel `ocr.json` et `traduction.json` s'alignent **par position**
(`manga/checkpoints.py`). Installer un cache d'une autre version ferait atterrir les
traductions dans les mauvaises bulles, sans un message. `import_build._version_des_regions` lit
donc la version **dans le JSON**, avec la même règle tolérante que le module d'origine (une
liste nue = v1).

### 1.3 Le téléchargement d'une release, et la vérification d'empreinte

| Mesure | Valeur | Dénominateur |
|---|---|---|
| poids de l'installeur 2.31.0 | **292,1 Mio** (306 242 994 octets) | 1 fichier, celui de `dist/` |
| SHA-256 de ce fichier | **0,27 s**, soit 1 062 Mio/s | 1 mesure, blocs de 1 Mio |
| débit sur un asset de release GitHub public | **2,5 Mio/s** | **1 mesure, 2,0 Mio lus**, connexion de cette machine |
| estimation pour 292 Mio à ce débit | **~115 s** | dérivée de la ligne ci-dessus |

> **Ce que ces chiffres décident** : la vérification d'empreinte est **gratuite** devant le
> téléchargement (0,27 s contre ~115 s), donc il n'y a aucune raison de la rendre optionnelle.
> Et ~115 s, c'est ce qui impose une barre de progression, un bouton d'annulation, et le fil de
> travail plutôt que le fil d'affichage.

⚠ **Ce que ces chiffres ne disent pas** : le débit est **une** mesure sur **une** connexion, et
2,0 Mio est un échantillon court — assez pour dire « deux minutes, pas deux secondes », pas
pour donner une durée. Il n'est pas mesuré sur l'asset réel, qui n'existe pas (cf. §4).

---

## 2. Le light novel — ce qui manquait, et la seule preuve qui compte

`manga/creation_projet.py` était **le seul module du dépôt qui écrive sous `sources/`**, et
`FORMATS = ("manga", "webtoon")`. Aucune fonction ne savait créer
`sources/<Projet>/<Tome>/<LANGUE>/` — l'arborescence de la brique **historique** du projet.
`app.py` se contentait de dire à l'utilisateur de faire le dossier à la main.

`creation.py` (racine, 218 lignes) porte trois **dispositions** :

| Disposition | Arborescence | Extensions acceptées |
|---|---|---|
| manga / webtoon | `<Tome>/<format>[/<LANGUE>]` | images + `.cbz .cbr .zip` |
| **light novel** | `<Tome>/<LANGUE>` — **sans le cran `<format>`** | `.docx .pdf .epub .txt .md` |

Le cran absent n'est pas une simplification : `pipeline/sources.py:_langues_presentes` fait un
`iterdir()` sur le dossier du **tome**. Insérer un `light_novel/` rendrait le tome invisible au
pipeline qui doit le lire.

> **La preuve qui compte** (`test_le_pipeline_reconnait_les_cinq_langues`) : un tome est créé
> **par langue**, et c'est le détecteur du pipeline — pas une assertion sur des noms de
> dossiers — qui doit le voir. Un dossier créé que le pipeline ignorerait serait pire qu'une
> absence de fonction, et rien dans le code de création ne le dirait.

**Ce qui ne bouge pas** : `manga/creation_projet.py` reste, et tout ce qui l'importe continue
de marcher (`test_le_module_manga_continue_de_fonctionner`).

### 2.1 Le glisser-déposer, et l'ambiguïté qu'on refuse de trancher

`gui/depot.py` gagne un verdict `SOURCES_LN` pour **`.pdf` et `.epub` seulement**.

⚠ `.docx`, `.txt` et `.md` **restent** `GLOSSAIRE`, et c'est une décision : ils sont déjà dans
`GLOSSAIRES_TEXTE`, et l'extension seule ne dit pas si le fichier est un glossaire rédigé à la
main ou un tome de roman. Le dépôt refuse de deviner ; le chemin explicite reste « Nouveau
projet ».

### 2.2 ⚠ Un test existant est devenu DANGEREUX, pas seulement faux

`test_un_lacher_inconnu_produit_un_message_pas_un_silence` employait un `.pdf` comme exemple
d'inconnu. Le lot en fait un tome de roman : le lâcher ouvrait donc « Nouveau projet »,
c'est-à-dire une **boîte modale**, et la suite entière se figeait **sans un mot de sortie**.

C'est ainsi que le couplage a été trouvé. Le test est **réécrit** — exemple `.psd`, propriété
inchangée — et doublé d'un test neuf qui affirme le comportement voulu
(`test_lacher_un_roman_propose_un_projet_light_novel`).

### 2.3 Un second défaut, et il ne vivait que dans la boîte montée

La liste « Langue source » n'était plus statique depuis ce lot : elle dépend de la disposition,
qui décide si « (langue par défaut du projet) » a un sens. Elle est recalculée par
`_maj_disposition`, branché sur `currentTextChanged` — **qui ne part pas à la construction**.

Résultat : la boîte s'ouvrait avec un combo de langue **vide** tant qu'on ne changeait pas de
format. Un manga se créait donc sans langue par accident, et un roman ne se créait pas du tout.

⚠ Le test qui l'a trouvé **interroge** le combo au lieu de le cliquer
(`[itemData(i) for i in range(count())]`). Un test qui aurait simulé un changement de format
aurait déclenché le signal manquant et serait passé au vert sur un défaut intact.

---

## 3. L'import d'un `build/` reçu d'un tiers

`import_build.py` (racine, 388 lignes, sans Qt) compare le `projet.json` entrant au local et
rend un **plan** : planches identiques / modifiées / ajoutées / absentes.

Le mécanisme d'identité n'a pas été inventé — `manga/projet.py` écrit déjà une **empreinte par
planche** sur les sept fichiers qui décident du rendu, délibérément insensible aux `mtime`,
« qui mentent — une synchronisation OneDrive les réécrit ».

**Trois refus, avant toute écriture :**

1. `projet` ou `tome` différents ⇒ refus. On n'installe pas le tome d'un autre ;
2. `FORMAT_VERSION` des `regions.json` entrants ≠ 3 ⇒ refus (cf. §1.2) ;
3. un run en cours ⇒ refus, comme les réparations.

**Ce qui est écrit, et rien d'autre** : les checkpoints des planches réellement différentes. Ce
qui existe localement et n'est pas dans le paquet n'est **jamais supprimé**. Ce qui est écrasé
part d'abord dans `.avant-import-<date>/` — même geste que `core/glossary_import.sauvegarder()`.

### 3.1 Un défaut trouvé par le test monté, et il rendait l'import impossible

`gui/dialogues.py:DialogueImportBuild._relire` appelait
`theme.poser_role(self.annonce, "erreur" if refus else "")`. Or `poser_role` **refuse un rôle
inconnu par un `KeyError`**, et `""` en est un. L'exception coupait `_relire` juste après cette
ligne : la liste des planches restait vide et le bouton « Importer » ne s'activait **jamais**.

Le module `import_build.py` était vert (21 tests) ; c'est le test **monté**
(`tests/test_gui_dialogues_maj.py`) qui l'a trouvé. C'est exactement ce que ce niveau de test
existe pour attraper — un défaut qui ne vit que dans le câblage.

---

### 3.2 Un troisième défaut, trouvé en relisant le câblage de la mise à jour

`_recevoir_maj_verifiee` retombait sur `_resultat_maj` — le résultat du dernier clic, gardé
pour toute la session — quand la tâche courante n'en portait pas. Or « Rafraîchir la liste des
modèles » est aussi une tâche `GENRE_SONDE` : après un clic sur « Rechercher une mise à jour »,
**chaque rafraîchissement de la liste des modèles aurait rouvert la fenêtre de proposition**,
sur un résultat qui date.

La correction tient en une ligne — une tâche répond de **son** résultat, jamais de celui d'une
autre — et elle a son test (`test_rafraichir_la_liste_des_modeles_ne_rouvre_PAS_la_proposition`).

⚠ **Les trois défauts de ce lot sont des défauts de câblage**, aucun n'est dans un module
testé sans écran : `creation.py`, `import_build.py` et `gui/vue_maj.py` étaient verts avec
56 tests pendant que la boîte s'ouvrait vide, que le bouton « Importer » ne s'activait jamais et
qu'une sonde de modèles rouvrait une fenêtre. C'est l'argument pour les 13 tests montés que ce
lot ajoute, après quatre lots qui n'en ajoutaient aucun.

---

## 4. La mise à jour — et le seul critère du plan qui n'est PAS tenu

### 4.1 Le prérequis, qui n'était rempli par rien

`publication.yml` crée bien une release sur un tag `v*`, **sans aucun fichier** (« ce lot livre
le squelette, pas l'artefact »), et le job `artefact` du lot 37 téléverse des **artefacts de
workflow**, qui ne sont pas des assets de release. Un updater qui aurait demandé « le dernier
asset publié » n'aurait donc **rien eu à télécharger**.

`ci.yml` attache désormais `dist/*.exe` et `dist/SHA256SUMS.txt` à la release, sur tag,
avec `permissions: contents: write` et une action tierce **épinglée au correctif**
(`softprops/action-gh-release@v2.0.8`) — comme les deux autres actions tierces du dépôt, et
d'autant plus qu'elle reçoit un jeton d'écriture.

### 4.2 ⚠ CE QUI N'EST PAS TENU : aucun aller-retour réel

> Le critère écrit du plan était : « une release de test avec ses assets, et une mise à jour
> 2.31.0 → suivante installée par le bouton, empreinte vérifiée ». **Il n'est pas tenu, et il
> ne pouvait pas l'être.**

Mesuré le 2026-09-06 :

```
GET https://api.github.com/repos/GNAlexandre/Angelith/releases/latest  ->  404 en 0,72 s
GET https://api.github.com/repos/GNAlexandre/Angelith                  ->  404
GET https://api.github.com/repos/GNAlexandre/Yume-Trad                 ->  404
```

Les **deux** dépôts sont privés — le miroir public l'est « jusqu'à la candidature NLnet »
(`docs/PUBLICATION-ANGELITH.md`), et aucune release n'y existe. Le chemin complet
« télécharger → vérifier → installer » est donc écrit et testé **contre des doubles**, jamais
contre une vraie release.

Ce qui est réellement vérifié, et ce qui ne l'est pas :

| Critère | État |
|---|---|
| lire les assets d'une release (nom, URL, taille) | ✅ testé sur un JSON de release |
| un JSON hostile ne fait pas lever | ✅ 5 cas paramétrés |
| lire l'empreinte attendue au format coreutils | ✅ y compris `*` binaire et nom à espaces |
| calculer l'empreinte d'un fichier | ✅ contre `hashlib` |
| le téléchargement rend la progression | ✅ sur un flux doublé |
| une annulation ne laisse **aucun** fichier partiel | ✅ |
| un réseau qui tombe en cours n'en laisse pas non plus | ✅ |
| **rien ne s'installe hors gel** | ✅ et **aucun `Popen` n'a lieu** |
| **un téléchargement réel depuis une release** | ❌ **impossible aujourd'hui** |
| **un installeur lancé par le bouton** | ❌ **non mesuré** |

### 4.3 Le 404 a changé la conception

Une vérification **armée par défaut** qui rendrait « Vérification impossible :
HTTPStatusError » serait, aujourd'hui, la seule chose que ce lot aurait livrée à tout le monde.
Deux décisions en découlent :

- `verifier()` traite le **404 avant `raise_for_status`** et rend « aucune version n'est
  publiée » — une absence, pas une erreur ;
- **la fenêtre ne s'ouvre JAMAIS sur un échec** (`vue_maj.doit_proposer` teste `disponible` et
  rien d'autre). Un échec de vérification ne sait pas s'il existe une version plus récente ;
  proposer sur un doute ouvrirait une fenêtre à chaque démarrage hors ligne.

### 4.4 Ce que l'empreinte protège, et ce qui est écrit à l'écran

Elle attrape un téléchargement **tronqué ou altéré en transit**. Elle **ne remplace pas une
signature de code** : aucun certificat ne signe ces binaires
(`docs/mesures/empaquetage-2026-09-06.md` §6.2), et le `SHA256SUMS.txt` vient de la **même
release** que l'exécutable, donc de la même main — elle ne protégerait pas d'un compte GitHub
compromis.

Le plan exigeait que cela soit « écrit à l'écran, pas seulement ici ». C'est
`gui/vue_maj.PHRASE_INTEGRITE`, affichée dans le corps de la fenêtre avant tout clic, et
`tests/test_gui_vue_maj.py` refuse qu'elle disparaisse.

### 4.5 La levée du lot 37, et ce qu'elle ne dit pas

L'affirmation « désarmé par défaut, et le motif est un différenciateur du produit » est
**levée** par un bloc daté dans `core/maj.py` **et** dans `config.yaml`, au-dessus de la clé.
Elle n'est pas effacée : elle décrit exactement ce que la 2.31.0 livrait.

Le motif de la levée : « 100 % local, rien ne sort de la machine » porte sur les **œuvres** —
aucun texte, aucune planche, aucun glossaire, aucune traduction ne quitte cette machine, et
cela reste vrai mot pour mot. La formulation de 2.31.0 mettait les deux dans le même sac.

⚠ **La clé absente vaut toujours `false`.** Une installation antérieure au lot 37 n'a pas la
section `maj:` et ne se met pas à appeler le réseau parce que personne ne lui a rien dit.

---

## 5. Les critères du plan, un par un

| Critère | État |
|---|---|
| L40.1 — « Light novel » dans la boîte de création, langue obligatoire | ✅ |
| L40.1 — `creation.py` à la racine, `manga/creation_projet.py` conservé | ✅ |
| L40.1 — `.pdf` / `.epub` au glisser-déposer, `.docx`/`.txt`/`.md` inchangés | ✅ |
| L40.2 — plan avant écriture, trois refus, sauvegarde, rien de supprimé | ✅ |
| L40.2 — la case « planches rendues », décochée, avec son chiffre | ✅ |
| L40.3 — la CI attache l'installeur et `SHA256SUMS.txt` à la release | ✅ **écrit, non exécuté** — aucun tag n'a été poussé |
| L40.3 — `core/maj.py` lit les assets | ✅ |
| L40.3 — bouton « Rechercher une mise à jour », empreinte vérifiée | ✅ testé sur doubles |
| L40.3 — hors gel, le bouton ouvre la page et n'installe rien | ✅ |
| L40.3 — check au démarrage armé, dans le **fil de travail** | ✅ il part avec les trois sondes |
| L40.3 — « Ne plus afficher », réversible depuis les Réglages | ✅ |
| L40 — un aller-retour de mise à jour réel | ❌ **§4.2** |
| L40 — création d'un tome LN réel puis `run.py --plan` | ⚠ **partiel** : la reconnaissance est prouvée par `pipeline.sources`, pas par un run |

---

## 6. Le compte de tests

| | avec PySide6 | sans PySide6 | écart |
|---|---|---|---|
| avant le lot 40 (2.33.0) | 4 912 | 4 496 | 416 |
| **après le lot 40** | **5 025** | **4 585** | **440** |

`python -m pytest --collect-only -q` et `python -m pytest --collect-only -q -p
tools.compte_sans_pyside`, 2026-09-06, toutes dépendances optionnelles installées.

**+113 tests**, dont **+89 sans Qt** — `tests/test_creation.py` (16), `tests/test_import_build.py`
(21), `tests/test_gui_vue_maj.py` (19), les ajouts de `tests/test_core_maj.py` et de `tests/test_empaquetage.py` — et **+24 avec
Qt** (`tests/test_gui_dialogues_maj.py`, plus un test de lâcher dans
`tests/test_gui_fenetre.py`). L'écart avec/sans PySide6 passe de 416 à **440** : ce lot est le
premier depuis le 36 à ajouter des tests qui exigent un écran, et c'est délibéré — le seul
défaut d'interface de ce lot (§3.1) n'était trouvable que monté.

⚠ Le « avant » est repris du tableau de `docs/plans/00-CONTEXTE-AGENT.md`, mesuré au lot 39, et
non recompté dans un `git worktree` propre. C'est la seule des deux colonnes qui ne soit pas de
première main aujourd'hui.

---

## 7. Ce que ce lot ne fait pas

- il ne rend **pas** le light novel utilisable sans LLM — limite nommée du lot 39, inchangée ;
- il ne **signe** aucun binaire, et la fenêtre de mise à jour le dit ;
- il ne livre **aucune** destination Scans, ni de paquet Linux ;
- il ne corrige **pas** les 150 échecs `manga-ocr` sans réseau — c'est un correctif à part,
  toujours ouvert ;
- il n'invalide **aucun** cache : `FORMAT_VERSION` reste à **3**.
