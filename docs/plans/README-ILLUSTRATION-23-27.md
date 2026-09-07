# Plans 23 à 27 — l'atelier d'illustration, destinés à Claude Code

Établis le **2026-08-27**, branche `main`, dépôt en **2.9.0** (`core/version.py`).

**Commencez par [`00-CONTEXTE-AGENT.md`](00-CONTEXTE-AGENT.md).** Il porte les conventions du
dépôt, la règle de numérotation, la convention de commit avec disclosure IA, les commandes, les
sept interdits et la définition de « terminé » en huit points. Cette série ajoute **trois choses
qu'il ne couvre pas** : une quatrième brique, un modèle génératif, et une obligation légale
datée. Elles sont traitées dans le `PLAN-24`, et **aucun autre plan de la série n'a le droit de
les contourner**.

**Un plan = une session = une branche = un `[X.Y.Z]`.**

---

## 1. Ce que la série fait, et ce qu'elle ne fait pas

Quatre questions ont été tranchées par Alexandre le 2026-08-27. Elles ne sont pas rouvrables par
l'agent :

| Question | Réponse arrêtée |
|---|---|
| À quoi servent les images ? | **Illustrations inédites pour ses propres tomes traduits.** Usage privé. Rien n'est publié, ni sur Kickstarter, ni dans une release, ni dans un document de mesure — sauf les images issues du seul corpus du domaine public (voir §5). |
| Périmètre du premier lot | **Un personnage seul, reconnaissable d'une image à l'autre.** Pas de scène, pas de planche multi-cases, pas de couverture typographiée. |
| Où tourne l'inférence | Sur la **7900XT (20 Go)**. Alexandre annonce « environ 10 Go en 4 bits » — c'est une **prémisse à mesurer**, pas un acquis (voir `PLAN-24` étape 0.3). |
| Quel modèle | **L'étape 0 du `PLAN-24` arbitre**, licence et VRAM vérifiées à la source primaire. |

**Ce que la série ne fait pas, et ne doit pas se mettre à faire en chemin :**

- elle ne touche **aucun pixel d'une planche ou d'une page de l'œuvre** — voir §4 ;
- elle ne produit **aucune planche manga** ni aucune mise en page à cases ;
- elle n'**affine aucun modèle** (LoRA, fine-tuning) sur un corpus sous droits sans que la
  question soit posée explicitement — le `PLAN-25` la pose, il ne la présume pas ;
- elle ne **publie** rien : ni image générée, ni recadrage de référence, ni nom d'œuvre.

## 2. Les cinq plans

| Plan | Objet | Nature attendue | Jours |
|---|---|---|---|
| [23](PLAN-23-LA-BIBLE-VISUELLE.md) | **La bible visuelle** : ce que le dépôt sait déjà d'un personnage **et du registre graphique du tome**, rassemblé et mesuré. Aucune image générée | MINEUR | 12 |
| [24](PLAN-24-LE-SOCLE-GENERATIF.md) | **Le socle** : la frontière écrite et testée, le run en deux phases, le moteur mesuré, le marquage légal | MINEUR | 12 |
| [25](PLAN-25-L-IDENTITE-TIENT-OU-NE-TIENT-PAS.md) | **L'identité, la nouveauté, le style** : trois grandeurs mesurées, conditionnement contre LoRA. Le seul plan qui peut se conclure par « on ne le fait pas » | MINEUR | 15 |
| [26](PLAN-26-LE-PROMPT-VIENT-DE-L-OEUVRE.md) | **La phase 1** : le LLM choisit les images et remplit la requête, l'humain valide ; forme du texte et canaux structurés mesurés | MINEUR | 10 |
| [27](PLAN-27-L-ATELIER-ET-LA-SORTIE.md) | **L'atelier** : écran de relecture de la requête, galerie, garder/jeter, insertion optionnelle et étiquetée | MINEUR | 10 |

**Total : 59 jours.** Ce n'est pas un programme à exécuter d'un bloc, et ce n'est pas non plus un
tout-ou-rien : **le `PLAN-23` a sa valeur propre même si la génération n'arrive jamais** (voir §3).

## 3. Ordre d'exécution, et pourquoi celui-là

1. **23 d'abord, sans exception.** Il ne génère rien. Il répond à la question que la série ne peut
   pas éviter : *le dépôt sait-il à quoi ressemble un personnage ?* La mesure du 2026-08-27 dit que
   non — sur les **5 projets** qui portent un `glossaire.yaml` vivant (sur 17 sous `sources/`),
   **171 personnages** sont déclarés, **171 ont un champ `role` vide (100 %)** et **150 ont
   `genre: '?'` (87,7 %)**, alors que `core/glossary.py` étiquette lui-même cette catégorie
   « Personnages (**le genre commande les accords**) ». Résoudre le genre depuis une illustration
   est un **gain de qualité de traduction**, indépendant de toute génération. C'est ce qui rend ce
   lot défendable seul.
2. **24 ensuite**, parce qu'il contient la frontière, le marquage légal et la mécanique des deux
   phases. Une ligne de code de génération écrite avant lui est une ligne à réécrire.
3. **25**, et c'est le plan qui décide si la série continue. S'il échoue, il échoue **avec un
   document de mesure**, et les plans 26-27 sont abandonnés — pas repoussés.
4. **26** puis **27**. Styler un atelier dont les images ne ressemblent à personne serait peindre
   une pièce sans mur.

Aucun de ces plans ne dépend des `PLAN-17` à `PLAN-22`, et aucun ne les bloque.

## 4. La frontière avec « l'IA ne dessine jamais », et elle est nette

**Décision d'Alexandre, 2026-08-27 : cette brique ne modifie aucune image existante. Elle en crée
de nouvelles. Le principe directeur n'est donc pas renégocié — il est hors sujet ici.**

`docs/README.fr.md` §« Principe : l'IA ne dessine jamais » énonce exactement ceci :

> « Détection et OCR ne font que **lire** l'image. Les seules écritures de pixels sont
> déterministes : `manga/clean.py` remplit le masque de bulle détecté avec sa couleur de fond
> mesurée, `manga/typeset.py` y dessine le texte traduit (Pillow). Aucun modèle génératif ne touche
> **au dessin**. Vérifié par `tests/test_manga_clean.py`. »

Lu littéralement, ce principe porte sur **le dessin de l'œuvre** : la planche scannée, la page
rendue. Il est répété à quatre endroits du code (`manga/orchestrator_manga.py` ≈ l. 3041,
`manga/relecture.py` l. 16, `manga/text_detection.py` l. 29, `docs/README.fr.md` l. 1820) et
**chacune de ces occurrences reste vraie mot pour mot après ce lot**, parce que la brique
d'illustration :

- n'ouvre **aucun** fichier de l'œuvre en écriture — les images de `media/` sont lues, jamais
  touchées ;
- n'appelle ni n'importe `manga/clean.py`, `manga/typeset.py` ou `manga/rendu.py` ;
- n'écrit que des fichiers **qui n'existaient pas**, dans un dossier qui lui appartient ;
- ne composite rien dans une planche ni dans une page.

⚠ **Ce n'est donc pas une décision doctrinale, c'est une clarification à écrire.** Trois raisons de
ne pas la sauter quand même :

1. **L'interdit n° 3 du `00-CONTEXTE-AGENT.md`** dit « `PLAN-22` est le seul plan autorisé à
   renégocier » le principe. Une session Claude Code qui lit cet interdit puis un plan de génération
   d'image s'arrêtera, et elle aura raison de s'arrêter. Il faut donc **une phrase de portée** dans
   `docs/README.fr.md` et dans l'interdit lui-même : *le principe porte sur les pixels de l'œuvre ;
   une brique qui ne touche à aucun pixel existant n'entre pas dans son périmètre.*
2. **La distinction doit être testée, pas seulement affirmée.** Le dépôt ne se contente jamais d'un
   raisonnement là où un test existe — `clean.py` garde son `paint &= region.mask` « parce que
   l'invariant ne doit pas dépendre d'un raisonnement ». Même exigence ici : `PLAN-24` L24.1 doit
   livrer un test qui **échoue** si `illustration/` ouvre en écriture un fichier existant, ou si
   elle importe un module de `manga/`.
3. **L'argument de communication est renforcé, pas affaibli.** « L'IA ne dessine jamais sur
   l'œuvre — et quand elle dessine, c'est ailleurs, dans un fichier neuf, marqué, et que vous avez
   demandé » se défend mieux devant NLnet qu'un principe absolu qu'un lecteur attentif trouverait
   contredit par une quatrième brique.

Le `PLAN-22`, lui, renégocie bien le principe : il propose d'effacer des pixels **de l'œuvre**. Les
deux sujets ne se mélangent pas, et **la phrase de portée de cette série ne doit pas servir de
précédent au `PLAN-22`** — dites-le explicitement là où vous l'écrivez.

## 4 bis. Comment un run se déroule — deux phases, un modèle à la fois

**Décision d'Alexandre, 2026-08-27.** La brique ne tourne jamais en même temps que la traduction, et
les deux modèles ne coexistent jamais en VRAM :

```
Phase 1 — LLM local (yume-27b, base Qwen 3.8 27B)
   entrées : bible.yaml, glossaire.yaml, texte traduit, images de media/
   sorties : le PROMPT proposé + la LISTE des images de référence retenues
             → écrits dans un fichier de requête, relisible

   ── PORTE HUMAINE ── l'utilisateur relit, corrige, valide, ou annule ──

Phase 2 — déchargement du LLM, chargement du modèle d'image
   entrées : la requête VALIDÉE + les images retenues
   sorties : les PNG marqués + leur sidecar de provenance
   fin : le modèle d'image est déchargé, le LLM peut revenir
```

Trois conséquences qui traversent les cinq plans :

- **La requête est un artefact persisté**, pas une variable. C'est elle qui rend la porte humaine
  possible, la reprise possible (`--from image`), et le rejeu possible.
- **La bascule de modèle a lieu une fois par run**, pas une fois par image. Sur 8 images, un
  va-et-vient par image coûterait plus que la génération elle-même — à mesurer, et à ne pas subir.
- **Aucune image n'est produite sans validation humaine du prompt.** Ce n'est pas une option de
  confort : c'est ce qui distingue « assisté » de « généré », la ligne exacte qu'exige la politique
  IA du dossier NLnet.

## 4 ter. Ce que la phase 1 produit exactement : pas « un prompt »

**Question posée par Alexandre le 2026-08-27 : et si l'artefact était un `.json` plutôt qu'un
prompt ?** La réponse tient en une distinction, et elle commande le format.

Le modèle d'image ne « lit » pas un fichier : il reçoit des **arguments typés**, et l'un d'eux
seulement est du texte, tokenisé par un encodeur qui est lui-même un LLM (`Qwen2.5-VL`). Dumper du
JSON dans ce champ ne gagne rien : les accolades et les guillemets coûtent des tokens et
n'apportent aucune structure au modèle. **La précision ne vient pas du format du texte, elle vient
des canaux qu'on utilise en plus du texte.**

Canaux réellement disponibles sur la famille Qwen-Image, vérifiés le 2026-08-27 :

| Canal | Ce qu'il contrôle | Comment il s'appelle |
|---|---|---|
| **prompt** (texte) | le contenu, le style, l'ambiance | chaîne tokenisée |
| **prompt négatif** | ce qu'on refuse | chaîne tokenisée |
| **images de référence** | **l'identité du personnage** | `edit_image` de `Qwen-Image-Edit-2511`, plusieurs images, désignées en prose (« image 1 », « la personne de l'image 2 ») |
| **entités + masques** | **la position et la forme de chaque élément** | `eligen_entity_prompts` + `eligen_entity_masks` (`Qwen-Image-EliGen-V2`, **Apache-2.0**, LoRA de 0,2 Md sur Qwen-Image) |
| **image de contrôle** | la pose, la composition | `blockwise_controlnet_inputs` (Canny/Depth) ou `context_image` (In-Context-Control-Union) |
| **paramètres** | graine, pas, CFG, dimensions | scalaires |

**D'où l'architecture retenue, et elle répond à la question par oui *et* non :**

1. **L'artefact que l'humain relit est un YAML** (`requete.yaml`), parce que le dépôt vit de fichiers
   commentés — `config.yaml` est « un document » de 95 Ko de prose justifiée, `glossaire.yaml` porte
   ses bannières et tous ses champs même vides. **JSON ne sait pas porter un commentaire**, et la
   porte humaine du §4 bis dépend entièrement de la lisibilité du fichier.
2. **Le payload envoyé au moteur est un JSON typé**, dérivé du YAML au moment de l'appel, et
   **archivé tel quel dans le sidecar de provenance** — qui est déjà un `.json`. C'est lui qui rend
   le rejeu exact possible.
3. **Le champ texte reste de la prose.** Sa forme optimale est une **question ouverte à mesurer, pas
   à hériter** : une source communautaire recommande des catégories étiquetées (Subject, Pose,
   Clothing, Camera, Environment, Lighting, Mood) en 1 à 3 phrases et annonce « +30 % de précision » ;
   une autre, sur le modèle d'édition, dit l'inverse — « il utilise un LLM comme CLIP, parlez-lui en
   langage naturel ». **Aucune des deux n'est mesurée sur ce corpus, et aucune ne porte de
   dénominateur.** `PLAN-26` étape 0.3 les met en concurrence sur les images d'Alexandre.

⚠ **Le gain de précision le plus élevé n'est pas dans le texte.** Il est dans les images de
référence (identité) puis dans les masques d'entités (position et forme). Un plan qui optimiserait la
syntaxe du prompt avant d'avoir mesuré l'apport des références se tromperait d'ordre de grandeur.

## 4 quater. Est-ce que la brique s'inspire vraiment des images du tome ?

C'est la question qu'Alexandre a posée le 2026-08-27, et elle a **deux moitiés qui n'étaient pas
traitées au même niveau** dans la première version de ces plans. Elles le sont maintenant :

| Moitié | Par quoi elle passe | État |
|---|---|---|
| **le bon personnage** (identité) | recadrages validés de `bible.references[]` → canal `edit_image` du modèle d'édition ; ressemblance et nouveauté mesurées | traité de bout en bout : `PLAN-23` L23.3/L23.5, `PLAN-25` L25.1/L25.2, `PLAN-26` L26.0 |
| **le bon registre graphique** (ne pas être « trop loin des images précédentes ») | `bible.style` : 2 à 5 **ancrages** validés + une **signature mesurée** du tome (palette, saturation, contraste, densité de trait, part d'aplats) → prompt et/ou canal d'images ; **distance de style** mesurée sur chaque génération | ajouté le 2026-08-27 : `PLAN-23` L23.7, `PLAN-25` étape 0.2 (échelle de style) et L25.1 (troisième grandeur), `PLAN-26` étape 0.2, `PLAN-27` L27.1 |

**Pourquoi les deux moitiés ne suffisent pas l'une sans l'autre :** une image peut être parfaite en
ressemblance, inédite au sens du plancher de nouveauté, et sortir un rendu photoréaliste là où le
tome est au trait. Ni la ressemblance ni la nouveauté ne l'attrapent — seule la distance de style le
fait. C'est pour cette raison que « ne pas traiter le style » n'est plus une option libre du
`PLAN-26` : elle ne se retient que si la mesure montre que les générations restent d'elles-mêmes dans
l'échelle du tome.

⚠ **Deux réserves honnêtes.** D'abord, la signature de style est calculée sur les illustrations
disponibles : un tome à 16 illustrations dont 6 exploitables donne une signature faible, et le champ
`echantillon` est là pour que personne ne l'oublie. Ensuite, une ancre de style qui montre un
personnage peut **contaminer l'identité** de l'image générée : `PLAN-26` étape 0.2 impose de préférer
des ancres sans visage — décor, objet, plan large —, c'est-à-dire précisément les illustrations qui
ne servaient à rien pour l'identité.

## 5. Le corpus, et la seule chose qu'on a le droit de montrer

Sur les 13 dossiers `build/*/*/media/` comptés le 2026-08-27, **404 fichiers** au total, dont
**164 pour le seul `Pride and Prejudice` Vol.1** et **1** pour `Demo LN` — soit **239 illustrations
sur 11 tomes de 10 œuvres** sous droits. ⚠ Ce compte est un `ls` dossier par dossier : il n'a pas
distingué une illustration d'une vignette de couverture ou d'un logo d'éditeur. Le refaire
proprement est l'étape 0.1 du `PLAN-23`.

Conséquence directe pour tous les documents de mesure de la série : **la seule œuvre dont une image
peut figurer dans un `docs/*.md` est `Pride and Prejudice`** (domaine public). Pour tout le reste,
les documents publient des **chiffres**, jamais des images, et **jamais le nom de l'œuvre** —
`.gitignore` exclut déjà `sources/` et `build/` en bloc, avec cette justification écrite :
« le dépôt devient public, et l'arbre git exposait alors le NOM de chaque œuvre comme nom de
dossier ». Ne la contredisez pas en déposant un recadrage de référence ailleurs.

## 6. Financement : cette série est hors périmètre, et c'est volontaire

Les tâches T1 à T7 du dossier NLnet et le périmètre Kickstarter (T3 + T5) ne contiennent **aucune**
tâche de génération d'image. Règle qui tient les deux dossiers : *jamais la même tâche financée
deux fois*. Cette série est donc du travail personnel, et deux conséquences en découlent :

- elle ne compte pas dans les jalons NLnet, et **ne doit pas apparaître comme un jalon** ;
- l'argument de souveraineté (« rien ne quitte la machine ») reste vrai, et l'argument
  « l'IA ne dessine jamais » reste **entièrement** dicible : la brique ne modifie aucune image de
  l'œuvre, et la phrase de portée du §4 le dit noir sur blanc. C'est un meilleur argument qu'avant,
  parce qu'il devient borné et testé plutôt qu'absolu et invérifiable.

## 7. Faits vérifiés en ligne le 2026-08-27

À revérifier à la source primaire au moment de l'exécution : ces modèles bougent tous les deux mois.

| Fait | Source |
|---|---|
| `Qwen-Image-2512` : **Apache-2.0**, **20 Md** de paramètres, sorti le 2025-12-31, texte-vers-image, ratios jusqu'à 1664×928 | [huggingface.co/Qwen/Qwen-Image-2512](https://huggingface.co/Qwen/Qwen-Image-2512), [github.com/QwenLM/Qwen-Image](https://github.com/QwenLM/Qwen-Image) |
| `Qwen-Image-Edit-2511` : **Apache-2.0**, 20 Md, sorti le 2025-12-23, **plusieurs images de référence**, « character consistency has been significantly improved » | [huggingface.co/Qwen/Qwen-Image-Edit-2511](https://huggingface.co/Qwen/Qwen-Image-Edit-2511) |
| `Qwen-Image-2.0` : annoncé le 2026-02-10, **7 Md**, 2K natif, génération et édition unifiées, « multi-panel comic generation with consistent characters ». **Licence non établie** — la page Hugging Face répond 401 | [github.com/QwenLM/Qwen-Image](https://github.com/QwenLM/Qwen-Image) |
| GGUF de `Qwen-Image-2512` : Q4_0/Q4_K_S **11,9-12,3 Go**, Q4_K_M **13,1 Go**, Q8_0 21,8 Go — **le transformeur seul**, encodeur de texte `Qwen2.5-VL-7B` et VAE non comptés | [guide GGUF, dev.to](https://dev.to/gary_yan_86eb77d35e0070f5/qwen-image-2512-gguf-complete-guide-to-running-ai-image-generation-on-consumer-hardware-1l6c) |
| ComfyUI Desktop : support **AMD ROCm officiel sous Windows** annoncé le 2026-01-06, ROCm 7.1.1, plantages signalés par des utilisateurs sur GGUF | [blog.comfy.org](https://blog.comfy.org/p/official-amd-rocm-support-arrives) |
| `Qwen-Image-EliGen-V2` : **Apache-2.0**, LoRA de **0,2 Md** sur Qwen-Image, contrôle par **entités** (`eligen_entity_prompts` + `eligen_entity_masks`) — position et forme de chaque élément | [huggingface.co/DiffSynth-Studio/Qwen-Image-EliGen-V2](https://huggingface.co/DiffSynth-Studio/Qwen-Image-EliGen-V2) |
| Autres canaux de contrôle documentés pour Qwen-Image : `Blockwise-ControlNet-Canny/Depth/Inpaint`, `In-Context-Control-Union`, `Qwen-Image-Layered`, `Edit-2511-Lightning`, LoRA et entraînement complet. **Aucune licence n'est indiquée variant par variant** dans cette page — à vérifier une par une | [DiffSynth-Studio, Model_Details/Qwen-Image.md](https://github.com/modelscope/DiffSynth-Studio/blob/main/docs/en/Model_Details/Qwen-Image.md) |
| DiffSynth annonce un plancher de **8 Go de VRAM** avec gestion d'offload (`onload_dtype`, `computation_dtype`, offload disque) — utile pour la mesure de l'étape 0.3 du `PLAN-24`, **pas** pour en déduire le temps par image | idem |
| Forme du prompt : deux conseils communautaires **contradictoires et non mesurés** — catégories étiquetées en 1 à 3 phrases avec « +30 % de précision » annoncés d'un côté, « parlez-lui en langage naturel, il utilise un LLM comme CLIP » de l'autre | [Civitai](https://civitai.com/articles/30826/qwen-image-2512-prompt-guide-and-best-practices), [HF discussion Edit-2511](https://huggingface.co/Qwen/Qwen-Image-Edit-2511/discussions/7) |
| **AI Act, art. 50(2)** : le fournisseur d'un système générant des images de synthèse doit les marquer dans un **format lisible par machine** et détectable. Applicable depuis le **2026-08-02** ; systèmes déjà sur le marché : jusqu'au **2026-12-02** | [artificialintelligenceact.eu](https://artificialintelligenceact.eu/transparency-rules-article-50/) |

⚠ Le dernier point est **en vigueur depuis 25 jours** au moment où ces plans sont écrits. Ce n'est
pas une précaution d'avenir, c'est une contrainte présente. Elle n'est pas un avis juridique : à
faire confirmer.

## 8. Trois écarts du dépôt constatés le 2026-08-27, à trancher

- **Le dernier commit est `ad5f6f0 [2.9.1] Sonar Issue Request`**, alors que `core/version.py`
  déclare `2.9.0` et que la première entrée du `CHANGELOG.md` est `## [2.9.0] - 2026-08-27`. Ou le
  message de commit annonce une version qui n'existe pas, ou la version n'a pas été incrémentée.
  `tests/test_version.py` ne compare que `version.py` au CHANGELOG : il ne voit pas cet écart.
- **`templates/reference.docx` n'existe pas.** Le `00-CONTEXTE-AGENT.md` §2 et la règle MAJEUR du
  `CHANGELOG.md` définissent tous deux un MAJEUR par « rupture du contrat de styles de
  `templates/reference.docx` » — or ce chemin ne contient plus que `reference.bak.docx` et
  `reference.2026-07-08-before-pagebreak.bak.docx`. Le vrai fichier a migré dans les packs de
  langue : `langues/fr/templates/reference.docx` et `langues/en/templates/reference.docx`, avec
  `rendu.reference_docx: null` en config qui délègue au pack. **La règle de numérotation du dépôt
  désigne donc un fichier qui n'est plus là.** À corriger dans les deux documents.
- **`role` est vide sur 171 personnages sur 171.** Le champ existe dans
  `core/glossary.py:FIELD_ORDER["personnages"]` depuis le début et n'a jamais été rempli, ni à la
  main ni par le terminologue. Soit il sert à quelque chose et le glossariste doit le remplir
  (`PLAN-23` L23.4), soit il ne sert à rien et il encombre 171 entrées.
