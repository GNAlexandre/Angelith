# Inventaire du couplage au français

> Livrable L1 du PLAN 01 (langue cible dynamique). **Un état des lieux, pas une proposition
> de correctif** : il existe pour que les étapes suivantes sachent ce qu'elles doivent router,
> et pour trancher la question du glossaire — celle qui décide si la refonte impose un MAJEUR.
>
> Établi sur la v1.8.0. Chaque entrée porte son chemin et sa ligne ; une ligne qui bouge ne
> rend pas l'inventaire faux, mais un item disparu doit être rayé, pas oublié.

## Résumé

Le couplage se répartit en **six classes**, très inégales en difficulté :

| Classe | Ampleur | Difficulté | Bloque quelle étape ? |
|---|---|---|---|
| 1. Chargement des prompts | **1 seul site** | triviale | étape 2-3 |
| 2. Guide de style | 4 sites | faible | étape 2-3 |
| 3. Gabarits de sortie (docx, css, styles) | 6 sites | faible | étape 4 |
| 4. Typographie en dur dans le code | 5 sites, dont **un lexique verbal français** | **moyenne à forte** | étape 4 |
| 5. Consignes françaises **écrites en Python** | **16 sites** (6 relevés d'abord, 10 de plus au lot 11) | moyenne | étape 3, et le plan ne les mentionne pas |
| 6. Schéma du glossaire + accords | 2 modules, dont un **entièrement français** | **forte** | étape 6 → **MAJEUR** |

**Les deux découvertes qui modifient le plan :**

- **La classe 5 n'était pas prévue.** Le plan suppose que « les huit fichiers de `prompts/` »
  portent la consigne de langue. C'est incomplet : des consignes de sortie française sont
  écrites **en dur dans le code Python**, hors de tout pack. Un pack `en` complet ne suffirait
  donc pas à produire de l'anglais — le titre de chapitre, le reformulage de naturalisation et
  la traduction unitaire manga resteraient français. Voir §5.

  > ⚠ **Et le relevé initial était lui-même incomplet.** Il s'arrêtait aux constantes NOMMÉES
  > et ne descendait pas dans les f-strings assemblées dans les listes `parts` de
  > `manga/orchestrator_manga.py` : il annonçait « ces six sites » sans en citer **une seule**
  > du chemin manga hors `traduction_unitaire.CONSIGNE`. Le lot 11 les a relevées une par une
  > — dix de plus, §5.2 ci-dessous.
- **La classe 1 est bien plus simple qu'annoncé.** Le plan demande de chercher dans quatre
  modules ; il n'y a **qu'un seul** point de chargement, `core/agents.py:168`, partagé par le
  light novel ET le manga. L'étape 3 est donc beaucoup moins risquée que le plan ne le laisse
  craindre.

---

## 1. Chargement des prompts — un seul site

| Où | Quoi |
|---|---|
| `core/agents.py:168` | `prompts_dir = Path(config["chemins"]["prompts"])` |
| `core/agents.py:246` | `prompts_dir / f"{nom}.md"` — le seul endroit qui ouvre un prompt |
| `config.yaml:364` | `chemins.prompts: "prompts"` |
| `core/config_schema.py:40` | clé `chemins.prompts` déclarée |

`manga/agents_manga.py` ne charge rien lui-même : sa docstring (ligne 25) acte qu'il passe par
le **même** `chemins.prompts` que le light novel. `scan/` n'utilise aucun prompt.

Les huit prompts sont `prompts/{correcteur, glossariste, manga_contexte, manga_onomatopees,
manga_traducteur, mise_en_page, terminologue, traducteur}.md`. **Les huit** nomment le français
comme langue de sortie.

> **Conséquence pour l'étape 3 :** router le chargement des prompts = modifier deux lignes de
> `core/agents.py`. C'est le point le moins coûteux de toute la refonte.

## 2. Guide de style

| Où | Quoi |
|---|---|
| `config.yaml:363` | `chemins.style_guide: "style_guide.md"` |
| `pipeline/orchestrator.py:833` | lecture, passe terminologie |
| `pipeline/orchestrator.py:1084` | lecture, passe traduction |
| `pipeline/render.py:498` | relecture pour le filtre de fuite |
| `pipeline/doctor.py:51-55` | vérification d'existence dans `--check` |

⚠ Un cas à ne pas manquer : `pipeline/orchestrator.py:182` `_looks_like_style_guide` détecte
qu'un modèle a **régurgité le guide** dans sa sortie, en cherchant le motif
`^#{1,6}\s*Guide de style\b` — **un titre français**. Sur un pack anglais dont le guide
s'intitulerait « Style guide », ce garde-fou serait muet. Il doit devenir une donnée du pack,
pas une constante.

## 3. Gabarits de sortie

| Où | Quoi |
|---|---|
| `config.yaml:340-341` | `rendu.reference_docx`, `rendu.epub_css` |
| `config.yaml:345-348` | `rendu.styles.dialogue: "List Paragraph"`, `rendu.styles.pensee: "Pensée"` |
| `config.yaml:350-353` | `rendu.metadata.langue: "fr"`, titre et auteur français |
| `templates/epub.css:26-27` | `.dialogue p::before { content: "— "; }` — **le tiret cadratin est dans le CSS** |
| `templates/epub.css:30` | `.pensee p { font-style: italic; }` — l'italique des pensées |
| `pipeline/orchestrator.py:1098, 1222, 1226` | injection des `custom-style` depuis `rendu.styles` |
| `pipeline/render.py:207-220` | `_sanitize_custom_styles` valide contre `rendu.styles` |
| `pipeline/doctor.py:80-92` | vérification d'existence dans `--check` |

Le garde-fou de `render.py:219` valide déjà contre `rendu.styles` **et non contre une liste
littérale** — contrairement à ce que le plan suppose à l'étape 4. Il suffira de lui donner
`pack.styles_word` à la place de `config["rendu"]["styles"]`.

## 4. Typographie en dur dans le code

| Où | Quoi | Gravité |
|---|---|---|
| `pipeline/render.py:229` | `_DIALOGUE_SPAN = re.compile(r'«\s*(.+?)\s*»')` — guillemets français | moyenne |
| `pipeline/render.py:234-243` | **`_SPEECH_VERB_START`** — une liste de ~40 verbes de parole français conjugués (`dit-il`, `hurla`, `murmura`…) | **forte** |
| `pipeline/render.py:244` | `_SENTENCE_END = re.compile(r'[;.!?…]')` | faible (quasi universel en écriture latine) |
| `pipeline/render.py:516-519` | `dialogue_dash_in_text`, `strip_dialogue_quotes` | faible (déjà en config) |
| `manga/typeset.py:213-214` | `_SUBSTITUTIONS` mappe `「」『』《》` vers **`«` et `»`** | moyenne |
| `manga/typeset.py:68+` | `majuscules: False`, `cesure_traits_union: True` | faible (déjà en config) |

⚠ **`_SPEECH_VERB_START` est le point dur de cette classe.** Ce n'est pas un caractère à
paramétrer, c'est un **lexique**. Il sert à décider si une incise reste collée à sa réplique —
une règle de segmentation de dialogue qui n'a pas d'équivalent mécanique en anglais, où l'usage
est `"...," he said`, sans inversion. Un pack ne peut donc pas se contenter de fournir une
autre liste : il doit pouvoir fournir une autre **stratégie**. À traiter comme une fonction du
pack, au même titre que `pack.accorder` (§6), et non comme une donnée.

## 5. Consignes françaises écrites en Python — **absent du plan**

Ces six sites construisent des messages envoyés au modèle, en dur, hors de `prompts/` :

| Où | Consigne |
|---|---|
| `pipeline/orchestrator.py:237` | « une phrase **française** plus idiomatique dit EXACTEMENT la même chose » |
| `pipeline/orchestrator.py:239` | « réécris pour un **français** fluide et idiomatique » |
| `pipeline/orchestrator.py:242` | « pour qu'elle sonne **française** » |
| `pipeline/orchestrator.py:269-271` | `system = "Tu traduis un TITRE de chapitre de light novel en **français** naturel…"` |
| `core/glossary_lang.py:273-275` | « ce que le lecteur **FRANÇAIS** lira […] traduction **française** s'il s'agit d'un nom commun » |
| `manga/traduction_unitaire.py:31` | `CONSIGNE = "Traduis en **français** la SEULE réplique…"` |

Les trois premiers forment le bloc `naturalisation.intensite`. Le quatrième est la traduction
des titres de chapitre. Le cinquième est la consigne de romanisation, dont la docstring
explique qu'elle est **délibérément** hors de `prompts/terminologue.md` (elle ne concerne que
les pivots CJK) — la raison reste bonne, mais l'endroit doit devenir un pack.

> **Conséquence :** l'étape 3 du plan (« router tous les accès par le résolveur ») doit couvrir
> ces six sites, sinon l'étape 5 livre un pack `en` qui produit du français sur quatre chemins.

### 5.2 Les prompts assemblés du chemin manga — relevé du lot 11

Le relevé ci-dessus s'arrête aux **constantes nommées**. Or l'essentiel du prompt manga n'est
pas une constante : il est assemblé ligne à ligne dans la liste `parts` de chaque fonction de
traduction. Ces sites décident réellement de ce que le modèle reçoit, et aucun n'était
inventorié.

**Ils ne sont pas externalisés ici** — c'est l'objet du lot 15. Le lot 11 les **nomme**, pour
que le lot 15 n'ait pas à refaire le relevé.

#### Six f-strings

| Où | Ligne | Contenu |
|---|---|---|
| `orchestrator_manga._lignes_gabarits` | `1823` | `f"{n}. {L}×{H} px — viser ≤ {budget} caractères"` |
| `orchestrator_manga._translate_lot` | `1934` | `f"— Planche {p.index} (bulles {depart} à {fin}) —"` |
| `orchestrator_manga._translate_lot` | `1961-1965` | la consigne de **numérotation continue** du lot |
| `orchestrator_manga._translate_page` | `2095-2096` | `f"Bulles détectées, en {langue} (ordre de lecture, {sens}) :"` |
| `orchestrator_manga._passe_contexte` | `2163-2164` | `f"Échantillon du texte en {langue} du tome :"` |
| `orchestrator_manga._translate_sfx` | `2239-2240` | `f"Zones de texte hors bulle, en {langue} (ordre de lecture, {sens}) :"` |

#### Quatre chaînes fixes, même problème de langue

| Où | Ligne | Contenu |
|---|---|---|
| `_translate_lot` | `1955` | « Répliques des planches précédentes (contexte, NE PAS retraduire) » |
| `_translate_lot` | `1958` | « Place disponible par bulle (dépasser force une police illisible) » |
| `_translate_page` | `2086` | « Répliques des planches précédentes (contexte, NE PAS retraduire) » |
| `_translate_page` | `2091` | « Place disponible par bulle (dépasser force une police illisible) » |

⚠ Les deux paires sont **des jumelles littérales**, et elles avaient déjà divergé : `2049`
disait « la planche précédente » au singulier alors que `manga.contexte.planches_precedentes`
en injecte **trois**. Corrigé au lot 11. C'est l'argument le plus net en faveur de
l'externalisation : deux copies d'une même phrase dans deux fonctions dérivent, et rien ne le
signale.

#### Et dans `manga/traduction_unitaire.py`

| Où | Ligne | Contenu | État |
|---|---|---|---|
| `CONSIGNE` | `31-33` | « Traduis en **français** la SEULE réplique… » | ✅ **surchargeable** par `pack.consigne(CLE_CONSIGNE, …)` — le seul point d'externalisation du chemin manga, et le lot 11 lui a enfin branché son pack |
| `prompt_bulle` | `93-94` | `f"Place disponible : {L}×{H} px — viser ≤ {budget} caractères."` | en dur |
| `prompt_bulle` | `95` | `f"Réplique en {langue} :"` | en dur |

**Total classe 5 : 16 sites** — 6 relevés à l'origine, 10 ajoutés par le lot 11.

### État : **clos par le lot 15 (L7.12)** pour le chemin manga

Les dix sites du §5.2 sont externalisés. Leur texte français vit désormais dans
`manga/consignes.py` — à son site d'appel, comme `traduction_unitaire.CONSIGNE`, et **pas**
recopié dans `langues/fr/pack.yaml`, qui déclare toujours `consignes: {}`. Le socle en
connaît les noms (`core.langues.CONSIGNES_CONNUES`), jamais le texte.

L'externalisation a été faite **avant** d'enrichir le prompt, et c'est l'ordre qui compte :
le lot 15 ajoute la structure de planche, le type de bulle et l'étiquette de locuteur à
l'énoncé. Écrites en dur, ces consignes auraient porté l'inventaire de 16 sites à 22, et
refait dans deux versions le travail que la 1.9.0 avait déjà fait une fois.

| Site (lot 11) | Clé de pack |
|---|---|
| `_lignes_gabarits`, la ligne de gabarit | `manga_gabarit_ligne` |
| `_translate_lot`, séparateur de planche | `manga_separateur_planche` |
| `_translate_lot`, numérotation continue | `manga_lot_consigne` |
| `_translate_page`, en-tête des bulles | `manga_bulles_entete` |
| `_passe_contexte`, en-tête d'échantillon | `manga_echantillon_entete` |
| `_translate_sfx`, en-tête hors bulle | `manga_hors_bulle_entete` |
| les deux « Répliques des planches précédentes » | `manga_precedentes_entete` |
| les deux « Place disponible par bulle » | `manga_gabarits_entete` |
| `prompt_bulle`, place disponible | `traduction_unitaire_place` |
| `prompt_bulle`, en-tête de réplique | `traduction_unitaire_replique` |
| `_libelle_ordre`, les deux sens de lecture | `manga_ordre_*` |

Et onze clés de plus pour ce que le lot 15 **ajoute** — groupes, types, locuteurs, appariement
image↔planche, crops ciblés, relecteur : cf. `langues/README.md`, section « Le chemin
manga », qui en tient la liste à jour.

⚠ **Ce qui reste ouvert, et qu'il vaut mieux écrire** : `{langue}` désigne la langue SOURCE,
et sort du français quel que soit le pack — il vient de `core/glossary_lang.py:NOMS`, relevé
au §5 ci-dessus et toujours couplé. Un run anglais annonce donc « source language japonais ».
C'est une ligne de la table `NOMS`, pas un site de prompt ; hors périmètre du lot 15.

⚠ Restent également en dur, et **délibérément** : les quatre noms de règle du relecteur
(`registre`, `accord`, `contradiction`, `glossaire`). `manga/relecture.py` les compare
littéralement pour décider si une correction est recevable ; les traduire ferait rejeter
toutes les propositions d'un pack non français. Les deux prompts le disent explicitement.

**Ce qui existe déjà et sert d'appui :** `core/glossary_lang.py:66-79` porte `NOMS`, une table
`code → nom lisible` (`"en": "anglais"`, `"de": "allemand"`…) avec une docstring qui explique
pourquoi un modèle a besoin du nom et pas du code. Elle n'est aujourd'hui utilisée que pour la
langue **source**. C'est exactement la brique dont la langue **cible** a besoin.

## 6. Glossaire — le point dur, et le verdict

### Le schéma est français dans sa forme

`core/glossary.py:49-59` — chaque entrée porte `nom`, `pluriel`, `genre`, `variantes`,
`termes_source`, `interdits`, `traduire`, `role`, `description`, `force`. Le champ `nom` est
**le rendu dans la langue cible**, mais rien dans le schéma ne dit *quelle* langue : il n'y a
qu'un seul emplacement. `genre` (`m`/`f`/`?`) n'a de sens que pour une cible à genre
grammatical.

`core/glossary_lang.py:9-14` acte la distinction « rendu français (`nom`) » / « graphie source
(`termes_source`) ». `core/glossary_lang.py:189` produit un message utilisateur qui dit
littéralement « n'a pas de rendu français ».

### Les accords sont français dans leur fond

`core/glossary_force.py` est **entièrement** français, et pas superficiellement :

| Ligne | Quoi |
|---|---|
| 19-20 | `_PLURAL_DET_SET = {"les", "des", "ces", "plusieurs", …}` |
| 21 | `_DET_FEM = {"une", "la", "cette", "ma", "sa", "ta", "toute"}` |
| 22 | `_DET_MASC = {"un", "le", "ce", "cet", "mon", "son", "ton", "tout"}` |
| 24 | `_ELISION_RE` — l'élision `l'` / `d'` / `qu'` |
| 27-30 | `_VOWEL_START` / `_CONSONANT_START`, le `h` étant exclu parce que muet ou aspiré est indécidable sans dictionnaire |

Sa docstring (lignes 41-50) porte le principe à préserver : **« le déterministe ne doit JAMAIS
introduire une faute que le modèle n'aurait pas faite »** — un remplacement dont le genre est
incertain est refusé, jamais fautif.

Le module se présente comme « ne connaissant que du texte brut et un glossaire : rien de propre
au light novel ». C'est vrai pour la brique, **faux pour la langue**.

### Verdict : oui, un MAJEUR — mais pas tout de suite

L'étape 6 du plan demande de trancher entre l'option A (glossaire multi-cibles) et B (un
fichier par langue). L'inventaire confirme la lecture du plan :

- **L'option A impose un MAJEUR.** Passer `{nom, pluriel, genre}` sous une clé `cibles.<code>`
  change le format de `glossaire.yaml`, que `core/glossary.py:118` charge et que
  `core/glossary_build.py` fusionne à chaque passe de terminologie. Une migration automatique
  est possible — le schéma est plat et régulier — mais tout glossaire existant est réécrit,
  donc « l'utilisateur doit éditer/regénérer », donc MAJEUR au sens du CHANGELOG.
- **L'option B ne tient pas la promesse du dépôt.** « Un nom cohérent entre le roman et son
  manga » repose sur le fait que `sources/<Projet>/glossaire.yaml` est **un seul fichier**
  partagé par les deux briques. Deux fichiers par langue dupliquent les `termes_source`, et
  rien ne garantirait qu'ils restent d'accord.

**Recommandation confirmée : option A, en 2.0.0**, et surtout **pas avant** que L2 et L3 aient
validé l'architecture de packs sur des chemins sans risque.

⚠ Un point que le plan ne dit pas : `genre` ne peut pas simplement descendre sous `cibles.fr`.
Il est lu par `core/glossary_force.py` **et** proposé au modèle dans les prompts. Une cible
sans genre grammatical (anglais) doit pouvoir omettre le champ sans que le schéma le réclame —
d'où l'intérêt de `pack.accorder()` avec une implémentation par défaut « ne rien faire », comme
le plan le prévoit.

## 7. Hors périmètre — classé, pas oublié

Le plan mentionne « messages de rapport et libellés qui apparaissent dans les fichiers
produits ». Ils sont français (`RAPPORT.md`, en-têtes de `perf.log`, avertissements de
`pipeline/orchestrator.py:1516` et `:1955`), mais ils décrivent **le run**, pas l'œuvre : ils
s'adressent au traducteur, pas au lecteur. Les traduire relève de l'internationalisation de
l'outil, un chantier distinct de la langue **cible de traduction**.

**À ne pas confondre**, sous peine de gonfler la refonte d'un facteur trois. Recommandation :
les laisser en français en L2-L4, et n'ouvrir la question qu'après.

## 8. Ce que l'inventaire change dans le plan

1. **Ajouter la classe 5 à l'étape 3.** Six sites de consignes en Python. Sans eux, le pack
   `en` de l'étape 5 ne produit pas de l'anglais.
2. **Alléger l'étape 3 sur les prompts.** Un seul site, pas quatre modules à ausculter.
3. **`_looks_like_style_guide` et `_SPEECH_VERB_START` sont des *fonctions* du pack**, pas des
   données. Les traiter comme des chaînes à paramétrer produirait un pack anglais qui segmente
   les dialogues selon des règles françaises.
4. **Le verdict glossaire est confirmé** : option A, 2.0.0, après L2 et L3.
