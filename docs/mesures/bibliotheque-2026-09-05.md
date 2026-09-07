# La bibliothèque des œuvres — l'état sur une page, le dépôt guidé, l'export du glossaire

**Lot 34** (`PLAN-34-LA-BIBLIOTHEQUE-DES-OEUVRES.md`) · livré en **2.28.0** · relevé du
**2026-09-05**.

| | |
|---|---|
| Commit de départ | `3e4259d` (2.27.0, lot 33) |
| Machine | Windows 11 Pro 10.0.26200, Python 3.12.3, PySide6 offscreen |
| Corpus | **18 dossiers sous `sources/`**, 16 sous `build/` — voir §1, le chiffre du plan est faux |
| Empreinte SHA-256 de `config.yaml` | `77cb4bf311ae654ff4b713f47b411b3a128901cacc90ad00a5abbf5cf3aedd6b` — **inchangée** avant et après : le lot n'ajoute ni ne modifie aucune clé |
| Outils livrés | `tools/inventaire_oeuvres.py` (le tableau, le chronomètre, le compteur d'appels système) |

Reproduire :

```powershell
python tools/inventaire_oeuvres.py --cout                 # le tableau et son coût
python tools/inventaire_oeuvres.py --markdown --anonyme   # ce qui est publiable
python run_manga.py --list                                # la sortie console, iso
python -m pytest -q tests/test_bibliotheque.py tests/test_glossary_export.py
```

Ce document reprend **les douze critères du plan un par un** (§8), y compris les **deux qui ne
sont pas tenus**, et publie ce que la mesure ne dit pas (§9).

---

## 1. Trois prémisses du plan étaient fausses. Les voici, avant le reste.

> « Un tableau qui ne confirme jamais que le plan n'est pas une mesure. »
> (`00-CONTEXTE-AGENT.md` §6)

### 1.1 Le corpus fait **18 œuvres**, pas 17

`docs/plans/00-CONTEXTE-AGENT.md` et les sept plans de la série 31-37 annoncent **17 projets
sous `sources/`**. Il y en a **18**, et ce n'est pas neuf : `docs/mesures/coquille-2026-09-04.md`
l'avait déjà relevé la veille, avec la même remarque. Le chiffre du plan a été recopié d'un
document daté sans être remesuré.

Le relevé complet, produit par le script livré :

| Grandeur | Valeur | Dénominateur |
|---|---:|---|
| œuvres | **18** | dossiers directement sous `sources/` |
| tomes | **55** | dossiers de tome, toutes briques confondues |
| unités source dénombrées | **3 493** | planches, bandes et pages — **les tomes indénombrables sont exclus** |
| tomes indénombrables | **15** | romans dont les chapitres ne sont connus qu'après extraction |
| glossaires | **14** | `sources/<Œuvre>/glossaire.yaml` présents |
| entrées de glossaire | **791** | toutes catégories, 14 fichiers |

Répartition par brique **principale** (un tome peut en porter deux, cf. §1.2) :

| Brique | Tomes |
|---|---:|
| Manga | 27 |
| Webtoon | 1 |
| Light novel | 26 |
| Scan (bêta) | 1 |

Total 55. ⚠ Ce sont les briques **principales** : `manga C / Vol.1` compte
pour un manga, alors qu'il porte aussi une brique scan.

### 1.2 Un tome peut porter **deux briques**, et le plan ne le prévoyait pas

`TomeInfo.brique` était déclaré `str` dans le plan. Le corpus contient un contre-exemple :
`sources/manga C/Vol.1/` porte **`manga/`** (165 planches, traitées et rendues)
**et** `JAP/` (271 images + son `.md` d'OCR, brique scan). Le champ singulier aurait fait
disparaître la moitié de ce tome de la vue.

Le modèle porte donc `brique` (la principale, pour décider quelles étapes afficher) **et**
`briques` (toutes, pour le filtre et le libellé). Le filtre de brique interroge `briques` :
filtrer sur « Scan » sans cela aurait fait disparaître le seul tome du corpus qui en porte un
aux côtés de ses planches.

### 1.3 ⚠ `core/bibliotheque.py` était **interdit par le dépôt**, et c'est testé

Le `PLAN-34` L34.1 demande le module « dans `core/` et non `manga/`, parce qu'il couvre les
deux briques ». **C'est exactement le raisonnement qui l'en exclut.** Deux tests existants le
refusent :

- `tests/test_core_alias.py:test_le_socle_ne_depend_pas_du_pipeline` ;
- `tests/test_core_cli.py:test_le_socle_nimporte_ni_les_briques_ni_les_cli`.

Ils interdisent à tout module de `core/` d'importer `manga`, `pipeline`, `run*` ou `app`. Le
socle est ce dont les briques dépendent ; y mettre un agrégateur de briques recréerait le
cycle que le lot qui a extrait `core/` de `pipeline/` avait défait. **La première version du
module a fait échouer ces deux tests** — c'est ainsi que la contradiction s'est vue.

Le module vit donc à la **racine** (`bibliotheque.py`), la couche qui est déjà au-dessus des
quatre briques : celle de `app.py`, `gui.py` et des quatre `run_*.py`. Il est importable par
les CLI, par `gui/` et par `tools/` sans inverser une seule dépendance.

### 1.4 Et une quatrième, dans `gui/depot.py` : le `.csv` n'était pas importable

`gui/depot.py` annonce depuis le lot 18 que « `.csv` est lu par le parseur tolérant de
`core.glossary_import`, qui accepte la tabulation et le point-virgule ». Mesuré le
2026-09-05 : **c'était faux deux fois.**

- `_to_text` ne connaissait que `.txt`, `.md` et `.docx` : un `.csv` levait
  `RuntimeError: Format non géré pour un glossaire` ;
- et le point-virgule ne figure pas dans `_SEPARATORS`.

Le lot livrant un **export** CSV, la promesse devait devenir vraie plutôt qu'être retirée :
`parse_file` route désormais le `.csv` vers un vrai lecteur CSV (§4.3).

---

## 2. Ce que le lot livre

| Fichier | Ce qu'il fait | Qt ? |
|---|---|---|
| `bibliotheque.py` | l'inventaire des 4 briques : `TomeInfo`, `Oeuvre`, `Inventaire`, la légende | **non** |
| `core/glossary_export.py` | YAML (archive) / CSV / Markdown (vues), provenance et pertes | **non** |
| `gui/depot_guide.py` | le parcours d'un lâcher : lecture, destination, collision, coût, refus `.cbr` | **non** |
| `gui/sorties.py` | ce qui existe sur le disque pour un tome, et ce qui n'existe pas | **non** |
| `gui/vue_oeuvres.py` | ce que la bibliothèque affiche : colonnes, filtres, pastilles, légende | **non** |
| `gui/oeuvres.py` | la destination « Œuvres » — le panneau, ses gestes, ses signaux | oui |
| `gui/dialogues.py` | `DialogueDepotGuide`, `DialogueExportGlossaire`, `DialogueSorties` | oui |
| `tools/inventaire_oeuvres.py` | le tableau du corpus, le chronomètre, le compteur d'appels | **non** |

Modifiés : `run_manga.py` (`--list` consomme l'inventaire), `gui/fenetre.py` (le balayage, les
cinq gestes, le lâcher guidé), `gui/travailleur.py` (`GENRE_BIBLIOTHEQUE`, sans verrou),
`manga/creation_projet.py` (`deplacer=`), `core/glossary.py` (`entete=`),
`core/glossary_import.py` (le `.csv`, les lignes de commentaire), et trois modules de lecture
d'état — voir §3.

**Les six modules NEUFS sont tous sans Qt** — `bibliotheque.py`, `core/glossary_export.py`, `gui/depot_guide.py`, `gui/sorties.py`, `gui/vue_oeuvres.py`, `tools/inventaire_oeuvres.py`. Les deux fichiers Qt du tableau ci-dessus (`gui/oeuvres.py`, `gui/dialogues.py`) existaient déjà et sont modifiés. C'est la règle de couche du dépôt, et c'est ce qui fait que **84 des 109 tests neufs** tournent dans le job de CI qui n'installe pas PySide6.

---

## 3. Étape 0.1 — le coût du balayage, et pourquoi il n'y a **pas** de cache

### 3.1 Le chiffre demandé par le critère 1

| Grandeur | Première version | **Livré** | Écart |
|---|---:|---:|---:|
| balayage complet (18 œuvres, 55 tomes), séquentiel | 2 205 ms | **1 436 ms** | −35 % |
| balayage complet, 4 fils | — | **1 250 ms** | −43 % |
| second affichage (mémoïsé) | 1,4 ms | **1,4 ms** | — |
| `os.stat` | 13 667 | **1 151** | **−92 %** |
| `os.scandir` | 2 082 | **2 095** | +0,6 % |
| `os.listdir` | 420 | **328** | −22 % |
| **total des appels système** | **16 169** | **3 574** | **−78 %** |

⚠ **Ce compte est un plancher, pas un total d'entrées-sorties.** Sous Windows, `os.scandir`
rend déjà les métadonnées de chaque entrée : un `DirEntry.stat()` qui suit ne touche pas le
disque et n'apparaît donc pas. Le chiffre se lit à côté du chronomètre, jamais à sa place.

### 3.2 Où passaient les 13 667 `stat`, et ce qui les a supprimés

Attribution par appelant, à l'instrumentation :

| Appelant | `stat` | Correctif |
|---|---:|---|
| `sources_manga.resoudre_source` L123 | **5 928** | `sorted(p for p in d.iterdir() if p.is_dir())` payait un `stat` **par entrée** — sur un `<Tome>/manga/` de 286 planches, 286 appels pour trouver zéro à trois dossiers de langue. Remplacé par `sources_manga.sous_dossiers()`, un `os.scandir` |
| `etat_planches.motifs_de_peremption` | **5 470** | cinq `stat` par planche pour une information que l'entrée de répertoire porte déjà. `etat_planches.balayer_tome()` lit tout un tome en un `scandir` par planche |
| `etat_planches.indices_de` L98 | **1 102** | même défaut, même correctif |
| le reste | 1 167 | — |

Et un doublon : `balayer_tome` était appelé **deux fois par tome** — une fois par la
bibliothèque pour ses comptes d'étapes, une fois par `serie.etat_chapitre` pour la péremption.
`etat_chapitre` accepte désormais un `balayage=` déjà fait : **2 607 `scandir` de dossiers de
planche sont devenus 1 304**.

⚠ **Aucun de ces trois correctifs ne change un verdict.** Le filtre et le tri sont identiques,
et la règle de péremption est écrite **une seule fois** (`etat_planches._motifs`), appelée par
les deux chemins d'accès — celui qui interroge le disque planche par planche pour l'éditeur, et
celui qui lit tout un tome pour la bibliothèque. `test_le_balayage_massif_et_le_balayage_planche_par_planche_sont_d_accord`
refuse qu'ils divergent.

Ils profitent aussi à `run_manga.py --list` et à l'éditeur, qui appellent les mêmes fonctions.

### 3.3 ⚠ Le cache demandé par le plan n'est **pas** livré, et c'est une décision

Le plan écrit : « mesurez le temps du balayage complet […]. Si c'est au-delà d'une seconde, il
faut un cache — et le cache a sa propre clé d'invalidation, à écrire. »

**Le balayage tient en 1,25 s. Le seuil n'est pas tenu, et le cache n'est pas livré.** La
raison n'est pas le temps, c'est la clé.

La seule clé d'invalidation assez bon marché pour valoir la peine serait le `mtime` des
dossiers de build. **Elle est fausse** : réécrire `traduction_manuelle.json` dans
`.checkpoints/page_0042/` ne déplace pas le `mtime` de `.checkpoints/`. Un tel cache afficherait
donc « à jour » sur un tome qu'on vient de corriger à la main — c'est-à-dire exactement le
défaut que `manga/etat_planches.py` existe pour empêcher, et qu'il documente en tête de module.

Ce qui est livré à la place, et qui n'a pas ce risque :

1. **la suppression de 78 % des appels système** (§3.2), qui bénéficie à tout le monde ;
2. **le balayage sur quatre fils** — il est bloqué sur le disque, pas sur le processeur ;
3. **la mémoïsation en mémoire**, pour la durée de l'affichage : refiltrer, retrier ou revenir
   sur la destination coûte **1,4 ms**, et c'est le geste répété ;
4. **le balayage hors du fil d'affichage** (`GENRE_BIBLIOTHEQUE`), de sorte que la seconde qui
   reste ne gèle pas la fenêtre ;
5. **un bouton « Rafraîchir » explicite**, et un balayage automatique après toute création de
   projet.

Le gain des fils, mesuré (médiane de trois balayages à froid, corpus complet) :

| Fils | 1 | 2 | **4** | 8 | 16 |
|---|---:|---:|---:|---:|---:|
| Balayage complet | 1 436 ms | 1 450 ms | **1 250 ms** | 1 394 ms | 1 714 ms |

Le plateau à quatre est net et le repli au-delà l'est aussi : ce qu'on parallélise n'est pas du
calcul, et un disque cesse de répondre plus vite au-delà d'une poignée de requêtes simultanées.

### 3.4 Le budget d'imports de `--list`, cassé puis réparé

`manga/serie.py` documente une règle : rien de lourd au niveau module, parce que numpy et
Pillow feraient passer `--list`/`--help` de 0,19 s à 0,46 s.

**La première version du lot l'a cassée**, et la mesure l'a montré :
`run_manga.py "manga C" --list` — six tomes qui n'ont jamais tourné —
importait numpy et PIL, là où la 2.27.0 ne les importait pas. Cause : `balayer_tome` était
appelé sans condition, et `manga.etat_planches` tire `manga.checkpoints`.

Le balayage est désormais gardé par l'existence de `.checkpoints/`. Vérifié des deux côtés :

| Commande | 2.27.0 | 2.28.0 |
|---|---|---|
| `--list "manga C"` (jamais traitée) | pas de numpy, pas de PIL | **pas de numpy, pas de PIL** |
| `--list "manga A"` (terminée) | numpy + PIL | numpy + PIL *(inchangé — `serie` les importait déjà)* |

Et les temps de bout en bout (médiane de cinq lancements de processus) :

| Commande | 2.27.0 | 2.28.0 |
|---|---:|---:|
| `--help` | 497 ms | **390 ms** |
| `--list` (racine) | 1 399 ms | **1 418 ms** |
| `--list` (œuvre jamais traitée) | 719 ms | **673 ms** |
| `--list` (œuvre terminée) | 1 941 ms | **1 918 ms** |

Les écarts sont dans le bruit de lancement d'un processus Python sous Windows. **`--list` ne
coûte pas plus cher qu'avant.**

---

## 4. Étape 0.2 — l'aller-retour du glossaire, avant la première ligne d'export

### 4.1 La forme RÉELLE des glossaires du corpus

Relevée sur les 14 fichiers, pas sur ce que le schéma autorise :

| Grandeur | Valeur |
|---|---|
| glossaires | 14 |
| entrées, toutes catégories | **791** |
| **le plus gros** | **manga D — 124 entrées, 38 359 octets** |
| suivants | roman N (109, 37 881 o), manga A (97, 27 570 o) |
| au format multi-cibles | **14 sur 14** — aucune migration à craindre |
| langues cibles présentes | **`fr` seulement**, sur les 14 |
| champs effectivement rencontrés | `cibles`, `termes_source`, `description`, `role`, `traduire`, `a_romaniser`, et `vo`/`fr` pour les anglicismes |

⚠ **Aucun glossaire du corpus ne porte de seconde langue cible.** L'invariant « exporter vers
le français n'efface pas le travail fait en anglais » n'est donc **pas** vérifiable sur le
corpus : il l'est sur un glossaire fabriqué qui en porte deux
(`test_l_export_yaml_garde_les_AUTRES_langues_cibles`). C'est une limite de la mesure, pas du
code, et elle est dite ici plutôt que passée sous silence.

### 4.2 Le test d'idempotence — écrit d'abord, passé sur les 14

`test_l_aller_retour_yaml_est_idempotent_sur_les_glossaires_REELS` : pour chacun des 14
fichiers, `lire_glossaire_yaml(export(g)) == lire_glossaire_yaml(g)`, **structures comparées,
jamais octets** (l'en-tête de provenance est justement neuf).

| Œuvre | Entrées | Aller-retour | Source intacte |
|---|---:|---|---|
| manga D | 124 | ✓ | ✓ |
| roman N | 109 | ✓ | ✓ |
| manga A | 97 | ✓ | ✓ |
| roman O | 76 | ✓ | ✓ |
| roman P | 73 | ✓ | ✓ |
| roman Q | 64 | ✓ | ✓ |
| roman R | 64 | ✓ | ✓ |
| roman S | 61 | ✓ | ✓ |
| manga C | 42 | ✓ | ✓ |
| roman_T | 32 | ✓ | ✓ |
| roman_U | 26 | ✓ | ✓ |
| manga B | 21 | ✓ | ✓ |
| webtoon A | 2 | ✓ | ✓ |
| Pride and Prejudice | 0 | ✓ | ✓ |

**14 sur 14.** Et la seconde colonne compte autant que la première : `glossary.load` MIGRE et
RÉÉCRIT le fichier qu'il ouvre. L'export passe donc par `yaml.safe_load` et la conversion en
mémoire, comme `glossary_import.lire_glossaire_yaml`, écrite pour cette raison exacte.

### 4.3 Ce que l'export perdrait — mesuré, pas supposé

Le plan demandait de « chercher ce que l'export perdrait ». Voici la mesure, sur les 14
glossaires réels, aller-retour CSV compris.

| Ce que le CSV conserve | Vérifié sur |
|---|---|
| noms, catégories | 14/14, ensemble identique |
| genres grammaticaux | 14/14 |
| variantes | 14/14 |
| formes interdites | 14/14 |
| descriptions | 14/14 |
| `termes_source`, `role`, `pluriel`, `force`, `traduire` | oui (test sur glossaire fabriqué) |

| Ce que le CSV perd | Pourquoi |
|---|---|
| les rendus des **autres langues cibles** | le fichier n'en porte qu'une, celle qu'on exporte |
| `a_romaniser`, et toute clé ajoutée à la main | hors colonnes |
| la différence entre un champ **vide** et un champ **absent** | `role: ''` et un `role` jamais renseigné reviennent identiques — sans conséquence, les deux valant « rien à dire » |
| les commentaires et la mise en page du YAML | — |

Le Markdown perd davantage, et le dit : il se relit très bien à l'œil, il **ne se réimporte
pas** — le parseur tolérant ne reconnaît pas les colonnes par leur titre, et une variante peut
y atterrir en guise de description.

⚠ **Les deux vues écrivent cette liste EN TÊTE du fichier produit** (critère 6), avec la
provenance complète : œuvre, tome d'où part l'export, version d'Angelith, date, nombre
d'entrées, langue cible.

### 4.4 Le défaut que l'export a révélé dans l'import

Un en-tête de commentaire qui dit « ⚠ ce fichier ne porte pas… » et qui se **réimporte en
fausses entrées** serait pire que pas d'avertissement du tout. Or c'est ce qui serait arrivé :
`_split_pair` découpait `# Le glossaire est propre à l'ŒUVRE : il vaut pour tous ses tomes.`
sur le « : » et en faisait un terme.

Deux règles ajoutées à `core/glossary_import.py`, toutes deux testées :

- une ligne commençant par `#` que `_detect_section` ne reconnaît pas est **ignorée** ;
- une citation Markdown (`>`) est **ignorée** — c'est de la prose, toujours.

---

## 5. Étape 0.3 — ce qu'« œuvre » veut dire, tranché

Une **œuvre** est un dossier de `sources/`. Elle porte un ou plusieurs **tomes**, chacun d'une
ou plusieurs briques déduites de son arborescence :

| Arborescence | Brique | Unité |
|---|---|---|
| `<Tome>/manga/…`, ou des images à plat sous `<Tome>/` | `manga` | planche |
| `<Tome>/webtoon/…` | `webtoon` | bande |
| `<Tome>/<LANGUE>/*.pdf .epub .docx .txt .md` | `ln` | chapitre |
| `<Tome>/<LANGUE>/*.png .jpg …` | `scan` | page |

Deux décisions valent d'être écrites :

1. ⚠ **le `<Tome>.md` que la brique scan écrit dans le dossier de langue ne compte pas comme
   une source de roman.** `scan/pages.py` l'exclut déjà de son propre balayage, ligne pour
   ligne ; le compter ici aurait fait basculer un tome de « scan à lire » à « roman » dès que
   l'OCR avait tourné, et fait disparaître sa brique de la vue ;
2. **la fonction de listage vit hors de `gui/`**, parce que la console en a besoin pour
   `--list`. Elle vit à la racine plutôt que dans `core/` — cf. §1.3.

---

## 6. Ce que la vue refuse d'afficher

| Refus | Motif |
|---|---|
| **aucune vignette d'œuvre**, même désarmée | ce sont des œuvres sous droit d'auteur, et une grille de couvertures est la capture d'écran qu'on ne pourra jamais montrer (`tools/captures_gui.py` porte déjà le raisonnement). Coût secondaire : 18 décodages d'image au premier affichage |
| **aucun run lancé depuis la bibliothèque** | « Lancer » amène à la destination qui annonce le coût, tome présélectionné, focus sur son bouton — comme `_aller_aux_runs` depuis la retouche |
| **aucune suppression** | la corbeille d'une application qui gère des heures de GPU est un lot à elle seule, avec sa confirmation et sa réversibilité |
| **aucun état dit par la couleur seule** | chaque état est un caractère distinct (`●◐○↻`), l'infobulle nomme chaque étape en toutes lettres, et la légende est dans la barre d'état **même repliée** |

`test_aucune_colonne_de_vignette` vérifie le premier point par lecture du source : ni `QPixmap`
ni `QIcon(` dans `gui/oeuvres.py`.

---

## 7. Le dépôt guidé, et le seul geste irréversible qu'il porte

| Règle du L34.3 | Ce qui est livré |
|---|---|
| ce que j'ai lu | fichiers, images, formats, poids ; **le contenu d'une archive listé sans l'extraire** (`test_une_archive_est_comptee_SANS_etre_extraite` remplace `ingest.extract_archive` par une fonction qui lève) |
| où ça va | projet et tome préremplis depuis le chemin, format déduit du chemin (**jamais des pixels**), corrigibles |
| copier, jamais déplacer par défaut | `deplacer=False` dans `creation_projet.copier`, case décochée, **non persistée**, et une confirmation nommant l'irréversibilité |
| la collision est nommée | « ⚠ ce dossier contient DÉJÀ 7 planche(s) » — nommée, mais **non bloquante** : `copier` renumérote les doublons plutôt que d'écraser, et bloquer priverait d'un ajout légitime |
| le compte rendu | le poids annoncé avant le premier octet, puis la ligne de journal qui dit ce qui a été écrit et où |

⚠ **Le `.cbr` est refusé AVANT l'import**, avec le motif exact : paquet `rarfile` absent, ou
outil externe `unrar`/`unar` introuvable dans le `PATH`. Aujourd'hui l'échec remontait en
`SystemExit` depuis `manga/ingest.py`, c'est-à-dire au milieu de la copie, après que
l'utilisateur avait nommé son projet.

> ⚠ **La sonde définitive appartient au `PLAN-36` L36.1, qui n'est pas livré.** Celle-ci est
> délibérément minimale — deux `which` et un `import` — et elle est écrite pour être
> **remplacée** par la sienne. Le plan disait « ce lot la consomme » ; il n'y avait rien à
> consommer, et le dire vaut mieux que de laisser croire que la dépendance est branchée.

---

## 8. Les douze critères du plan, un par un

| # | Critère | Verdict |
|---|---|---|
| 1 | tableau des œuvres publié, produit par un script livré, avec temps et compte d'`os.stat` | ✅ §1.1 et §3.1 — **et le corpus fait 18 œuvres, pas 17** |
| 2 | le modèle ne connaît ni Qt, ni PIL, ni aucun modèle ; un test vérifie **par instrumentation** qu'un balayage n'ouvre aucune image | ✅ `test_le_balayage_n_ouvre_aucune_image` remplace `PIL.Image.open` par une fonction qui lève ; `test_le_module_n_importe_ni_qt_ni_pil_ni_numpy` lit l'AST |
| 3 | `run_manga.py --list` consomme le même modèle ; sortie console iso, ou le CHANGELOG dit ce qui change | ✅ **iso, comparée ligne à ligne** sur les 18 œuvres (110 lignes, `diff` vide). Le coût aussi (§3.4) |
| 4 | « périmé » a exactement le sens de `_planches_perimees` ; test sur un tome fabriqué | ✅ `test_perime_a_exactement_le_sens_de_planches_a_relettrer` compare au retour de `etat_planches.planches_a_relettrer` sur un tome où la planche 2 a été éditée après son rendu |
| 5 | idempotence export → import sur les glossaires **réels**, le plus gros nommé | ✅ §4.2 — 14/14, **manga D, 124 entrées, 38 359 octets** |
| 6 | tout export non idempotent porte, **dans le fichier**, ce qu'il perd et sa provenance | ✅ §4.3, testé pour CSV et Markdown |
| 7 | dépôt guidé : copie par défaut, déplacement sur case cochée, collisions nommées, `.cbr` refusé avant | ✅ §7 |
| 8 | aucun bouton d'export ne lance un run sans confirmation nommant son coût ; le refus de PSD est un état | ✅ le geste est une **chaîne**, jamais un appelable (`test_aucune_sortie_ne_lance_un_run`) ; `REFUSEE` est un état distinct |
| 9 | aucune vignette d'œuvre réelle par défaut, aucune capture livrée n'en contient | ✅ §6, et **aucune capture n'est livrée du tout** (§9.6). ⚠ Le critère porte sur les IMAGES, pas sur les titres : ce document en nomme quelques-uns là où le plan l'exige (le plus gros glossaire, critère 5) et fournit `--anonyme` pour le tableau des 55 tomes, qui est le seul à décrire l'avancement œuvre par œuvre |
| 10 | pastilles avec légende, jamais la couleur seule | ✅ §6 |
| 11 | `ruff check .` et la boucle courte passent | ✅ §10 |
| 12 | ce document reprend les critères un par un, y compris les non tenus | ✅ |

### Les deux critères **non tenus**, nommés

- ⚠ **critère 1, seconde moitié** — le plan conditionne un cache au dépassement d'une seconde.
  Le balayage tient en **1,25 s** : le seuil est dépassé et **le cache n'est pas livré**. Le
  motif est en §3.3 : la clé d'invalidation praticable est fausse, et un cache qui affiche « à
  jour » sur un tome corrigé à la main est pire qu'un balayage d'une seconde. Ce qui est livré
  à la place est chiffré.
- ⚠ **L34.3, dernier point** — « la détection appartient au `PLAN-36` L36.1 ; ce lot la
  consomme ». Le `PLAN-36` n'est pas livré : il n'y avait rien à consommer. Une sonde minimale
  est livrée **en attendant**, et son module dit qu'elle doit disparaître au profit de celle du
  lot 36 (§7).

---

## 9. Ce que la mesure ne dit pas

1. **Rien n'a été mesuré sur un dossier synchronisé.** Le corpus est en local. Le compte
   d'appels système (§3.1) est le chiffre qui vaut pour un OneDrive, où chaque appel coûte cent
   fois plus — mais le **temps** de 1,25 s ne s'y transpose pas, et personne ne l'a mesuré.
2. **Une seule machine, un seul système de fichiers.** Sous Linux, `DirEntry.stat()` fait un
   vrai appel : le gain de `balayer_tome` y sera plus faible que les −92 % relevés ici. La
   suppression des `stat` de `resoudre_source`, elle, tient partout.
3. **L'invariant multi-cibles de l'export n'est pas vérifié sur le corpus**, faute de second
   `cibles.<code>` dans les 14 glossaires (§4.1). Il l'est sur un glossaire fabriqué.
4. **Le refus de PSD n'est pas confirmé, seulement compté.** Le panneau compare les `.psd`
   présents aux planches rendues, nomme la cause connue (le plafond de 30 000 px de
   `manga/psd.py`) et **dit qu'il ne la confirme pas** : la confirmer demanderait de lire la
   taille de chaque planche, soit un décodage d'image, soit ~150 lectures de `regions.json`
   (mesurées à ~1 s par tome par `etat_planches`). Aucun tome du corpus n'est actuellement dans
   cet état — **le chemin d'affichage n'a donc été exercé que sur un tome fabriqué.**
5. **Le déplacement (`deplacer=True`) n'a jamais tourné sur une vraie archive de 400 Mo**, ni
   entre deux volumes. `shutil.move` est utilisé précisément pour ce cas (il retombe sur
   copie + suppression quand `rename` échoue), mais ce chemin n'est testé que sur des fichiers
   de trois octets.
6. **Aucune capture d'écran de la bibliothèque n'est livrée.** Une capture utile montrerait le
   corpus réel, donc des titres sous droit d'auteur ; le tome synthétique de
   `tools/captures_gui.py` en montrerait un seul, ce qui ne dirait rien d'une liste. Le tableau
   anonymisé de §1.1 est ce qui remplace la capture.
7. **La destination n'a pas été mesurée à l'usage.** On sait ce qu'elle coûte à afficher ; on ne
   sait pas si ses sept colonnes sont les bonnes. C'est une question à reposer après quelques
   semaines d'usage réel, pas à trancher ici.

---

## 10. Vérifications finales

```
ruff check .                                            → All checks passed!
python -m pytest -q -m "not modeles and not lent"       → 4 430 exécutés, 57 désélectionnés
python run_manga.py --list  (18 œuvres, 110 lignes)     → diff vide avant/après
sha256(config.yaml)                                     → 77cb4bf3… inchangé
```

### Le compte de tests

| | avec PySide6 | sans PySide6 | écart |
|---|---:|---:|---:|
| après le lot 33 (2.27.0) | 4 378 | 4 039 | 339 |
| **après le lot 34 (2.28.0)** | **4 487** | **4 123** | **364** |

**+109 tests, dont 84 sans Qt.** Les deux colonnes ont été relevées — ce n'est pas une
déduction. Reproduire : `python -m pytest --collect-only -q` et
`python -m pytest --collect-only -q -p tools.compte_sans_pyside`.

⚠ **Les 84 sans Qt tiennent à une correction faite en cours de route.** Les décisions
d'affichage de la bibliothèque — colonnes, filtres, pastilles, légende — étaient d'abord
écrites dans `gui/oeuvres.py` ; leurs tests, qui n'ont besoin d'aucun écran, étaient alors
**impossibles à collecter** sans PySide6, et la collecte s'arrêtait en erreur sur ce seul
fichier. Elles vivent maintenant dans `gui/vue_oeuvres.py`, sans Qt — le pendant exact de
`gui/pellicule.py` pour la pellicule.
