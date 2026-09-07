# Procédure — light novel (`run.py`)

Traduire un tome de roman illustré, d'un `.docx` / `.epub` / `.pdf` / `.txt` / `.md` vers un
`.docx`, un `.epub` et un `.pdf` en français.

---

## 1. Poser le tome

```
sources/<Projet>/<Tome>/<LANGUE>/<un fichier source>
```

`<LANGUE>` est un dossier : `ENG`, `JAP`, `FR`… La correspondance dossier → code est
`langues.dossiers` dans `config.yaml`. Le glossaire de l'œuvre est **au niveau du projet**, pas
du tome : `sources/<Projet>/glossaire.yaml` — il sert à tous ses tomes.

```
sources/Mon LN/
├── glossaire.yaml          ← une seule fois pour l'œuvre
├── Vol.1/
│   ├── ENG/Vol.1.epub
│   └── JAP/Vol.1.epub      ← facultatif : sert de source d'appoint
└── Vol.2/…
```

⚠ **Un dossier `FR` change le mode.** S'il existe, le run passe en **amélioration** : le
français devient la base et les autres langues servent à le corriger, au lieu d'être traduites.

## 2. Vérifier avant de dépenser du GPU

```powershell
python run.py --check                          # serveur LLM, modèles, pandoc, polices, pack de langue
python run.py --list                           # les projets disponibles
python run.py "Mon LN" --list                  # les tomes d'un projet
python run.py "Mon LN" Vol.1 --plan            # le découpage en chapitres, sans traduire
python run.py "Mon LN" Vol.1 --dry-run         # toute la tuyauterie, aucun appel LLM
```

`--plan` est le geste qui évite la mauvaise surprise : un découpage à 1 chapitre sur un tome
qui en a 12 se voit en dix secondes, et se corrige par `decoupage.chapter_patterns`.

## 3. Traduire

```powershell
python run.py "Mon LN" Vol.1                   # le cas normal
python run.py "Mon LN" --all                   # toute la série, tome après tome
python run.py "Mon LN" Vol.1 --keep-awake --shutdown    # run de nuit, extinction annulable
```

Les cinq étapes, dans l'ordre : **`terminologie` → `traduction` → `correction` →
`mise_en_page` → `rendu`**. Chacune est mise en cache ; relancer la commande reprend au bloc
suivant.

```powershell
python run.py "Mon LN" Vol.1 --stop            # dans un AUTRE terminal : arrêt propre
python run.py "Mon LN" Vol.1 --from correction # ne refait que correction → mise en page → rendu
python run.py "Mon LN" Vol.1 --chapitre 3      # refait le chapitre 3 en entier
python run.py "Mon LN" Vol.1 --force           # refait les chapitres déjà faits
python run.py "Mon LN" Vol.1 --render-only     # régénère docx/epub/pdf depuis le .md existant
```

`Ctrl+C` fait la même chose que `--stop`. L'unité d'arrêt est le **bloc**, pas le chapitre.

## 4. Le glossaire, qui est le vrai levier de qualité

```powershell
python run.py "Mon LN" --extract-glossary      # relève les termes sans traduire
python run.py "Mon LN" --optimize-glossary     # dédoublonne, fusionne les variantes, reclasse
python run.py "Mon LN" --import-glossary fichier.docx
```

Deux champs comptent plus que les autres, et ils sont dans la catégorie « Personnages
(**le genre commande les accords**) » :

- **`genre`** décide de « elle est arrivée » contre « il est arrivé ». Le laisser à `'?'`, c'est
  laisser le modèle deviner à chaque bloc ;
- **`force: true`** impose `nom` comme traduction obligatoire : toute forme listée en
  `variantes` / `interdits` est remplacée dans le texte final, déterministement.

Pour aider à remplir `genre` depuis le texte et les illustrations du tome, voir
[bible-visuelle.md](bible-visuelle.md).

## 5. Lire ce qui est sorti

```
build/<Projet>/<Tome>/
├── <Projet>_<Tome>.md      ← le Markdown complet, source du rendu
├── <Projet>_<Tome>.docx / .epub / .pdf
├── chapters/chNN.md        ← un fichier par chapitre
├── media/                  ← les illustrations extraites
├── RAPPORT.md              ← à lire : ce qui a coincé
└── perf.log                ← temps et tokens
```

```powershell
python run.py "Mon LN" Vol.1 --diff-stages     # ce que chaque agent a réellement apporté
python run.py "Mon LN" Vol.1 --verbose         # temps et tokens en direct
```

---

## Les clés de `config.yaml` qui changent le résultat

### Ce qu'on touche le plus souvent

| Clé | Défaut | Effet |
|---|---|---|
| `naturalisation.intensite` | `0.60` | l'ampleur du reformulage autorisé au traducteur. `0.0` = fidèle et calqué, `1.0` = français de roman publié. Paliers : ≤0,15 minimal · ≤0,45 léger · ≤0,75 modéré · >0,75 marqué. ⚠ **C'est une intensité, pas un quota** — ce n'est pas « 10 % des phrases » |
| `langues.sources_utilisees` | `[fr, en, jp]` | les langues réellement lues. `[en]` = traduire depuis l'anglais seul ; en amélioration, **inclure `fr`** |
| `langues.priorite_sens` | `[en, jp, es, zh]` | quelle langue devient le **pivot** (la première présente gagne) |
| `langues.cible` | `fr` | le pack de langue de sortie. ⚠ Un pack absent ou incomplet **arrête le run au démarrage** — jamais de repli silencieux |
| `rendu.formats` | `[docx, epub, pdf]` | ce qui est produit. En retirer accélère `--render-only` |
| `modeles.correcteur` | `null` | l'agent de correction est **désarmé** par défaut. Le renseigner ajoute une passe LLM par bloc |

### Le découpage, quand `--plan` donne un résultat faux

| Clé | Défaut | Effet |
|---|---|---|
| `decoupage.chapter_patterns` | `[Prologue, Chapitre, Epilogue, …]` | les têtes de titre qui ouvrent un chapitre. **La première chose à corriger** quand `--plan` se trompe |
| `decoupage.detection` | `auto` | `auto` retombe sur un découpage LLM si le déterministe échoue |
| `decoupage.max_block_chars` | `6000` | taille d'un bloc envoyé au traducteur |
| `decoupage.max_block_tokens` | `2200` | le vrai plafond, en tokens ; le plus contraignant des deux gagne |
| `decoupage.epub.ruby` | `ignorer` | que faire des furigana d'un EPUB japonais |

### Les garde-fous — à ne desserrer qu'avec une mesure

| Clé | Défaut | Effet |
|---|---|---|
| `garde_fous.perte_mots_ratio.traducteur` | `0.60` | en dessous de ce ratio de longueur, la sortie du bloc est **rejetée** et rejouée |
| `garde_fous.redecoupage_sur_echec` | `true` | un bloc qui échoue est recoupé et rejoué, jusqu'à `redecoupage_profondeur_max` |
| `garde_fous.cjk_residuel_seuil` | `1` | nombre de caractères CJK tolérés dans une sortie française |
| `garde_fous.abandon_apres_timeouts_consecutifs` | `3` | arrête le tome plutôt que de tourner à vide toute la nuit |

### Le LLM

| Clé | Défaut | Effet |
|---|---|---|
| `llm.base_url` | `http://localhost:11434/v1` | le serveur Ollama |
| `llm.num_ctx` | `32768` | fenêtre de contexte. La monter coûte de la VRAM |
| `llm.timeout` | `900` | plafond par requête, en secondes |
| `llm.endpoints.reflexion.think` | `true` | l'endpoint « raisonnement ». Un agent le cible par `{model: …, endpoint: "reflexion"}` |
| `llm.thinking_budget` | `16000` | tokens ajoutés au plafond de sortie pour un agent qui raisonne |
| `modeles.<agent>` | `yume-27b` | le modèle par agent. `null` **désactive** l'agent |
| `temperatures.<agent>` | 0.0 à 0.5 | `mise_en_page` est à `0.0` : c'est du formatage, pas de la création |

⚠ **Le raisonnement n'est pas gratuit.** Mesuré sur un bloc japonais de ~5 600 tokens :
`think: "medium"` a envoyé **74 à 97 % de la génération dans le `<think>`** — 14 000 à
22 000 tokens de raisonnement pour 600 à 4 800 de traduction. C'est pourquoi seuls trois
agents ciblent `reflexion`.

---

## Quand ça ne marche pas

| Symptôme | Où regarder |
|---|---|
| `--plan` ne trouve qu'un chapitre | `decoupage.chapter_patterns`, puis `decoupage.detection: "auto"` |
| Des noms propres changent d'un chapitre à l'autre | le glossaire : `variantes`, puis `force: true` |
| « il est arrivée » | le champ `genre` du personnage dans `glossaire.yaml` |
| Des caractères japonais dans la sortie | `garde_fous.cjk_residuel_seuil`, et le `RAPPORT.md` du tome |
| Le rendu perd la mise en forme des dialogues | `rendu.styles.dialogue` doit porter le nom **XML exact** du style de ton `reference.docx` |
| Le run s'arrête au démarrage sur le pack de langue | c'est voulu : `langues.cible` désigne un pack absent ou incomplet, et le message liste les packs disponibles |
| Une illustration manque dans le rendu | elle précède peut-être la première frontière de chapitre — voir la section « tête de volume » de [bible-visuelle.md](bible-visuelle.md) |

**Toujours lire `build/<Projet>/<Tome>/RAPPORT.md`** avant de conclure quoi que ce soit : il
nomme les blocs rejoués, les pertes de longueur et les termes du glossaire manqués.

Pour les drapeaux non listés ici, voir [`../COMMANDES.fr.md`](../COMMANDES.fr.md) §
« Light novel ».
