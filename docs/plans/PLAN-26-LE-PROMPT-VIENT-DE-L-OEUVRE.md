# PLAN 26 — La phase 1 : le prompt vient de l'œuvre, et l'humain le valide

> **Lire `00-CONTEXTE-AGENT.md` puis `README-ILLUSTRATION-23-27.md` d'abord.**
>
> **Nature attendue** — **MINEUR**, avec une réserve : ce lot crée des **fichiers de prompt**, et
> l'entrée de CHANGELOG doit les nommer un par un (règle MINEUR du `CHANGELOG.md` : « toute
> réécriture de prompt qui change le caractère de la traduction… l'entrée doit nommer le fichier »).
> Ici les prompts ne touchent pas la traduction, mais la convention s'applique quand même : c'est
> elle qui permet à `git checkout <tag> -- langues/` de reproduire un résultat.
>
> **Charge estimée** — 10 jours (8 + 2 pour les étapes 0.3 et 0.4, ajoutées le 2026-08-27).
>
> **⚠ Prérequis : `PLAN-25` conclu positivement.** Si l'identité ne tient pas, ce lot est sans objet.
>
> **Ce lot est la phase 1 du run**, telle que le `PLAN-24` étape 0.1 bis la fixe : le LLM local
> (`yume-27b`, base Qwen 3.8 27B) lit l'œuvre, **choisit les images de référence**, rédige le prompt,
> et s'arrête. Il ne charge jamais le modèle d'image et n'en produit aucune. Sa sortie est un
> `requete.yaml` que l'utilisateur relit, corrige et valide — et **c'est cette validation qui est le
> livrable du lot**, pas le prompt.

---

## 1. Le constat

À la fin du `PLAN-25`, la brique sait produire une image qui ressemble à un personnage. Elle le fait
depuis une requête écrite **à la main**. Ce lot supprime la main.

Le matériau est déjà là, et il est de bien meilleure qualité que ce qu'un utilisateur taperait :

| Source | Ce qu'elle apporte | Où |
|---|---|---|
| `bible.yaml` | attributs visuels **cités**, références validées | `PLAN-23` |
| `glossaire.yaml` | le nom canonique, les variantes, le genre, la description narrative | `core/glossary.py` |
| le texte traduit | la scène, la tenue du moment, l'émotion, l'heure, le lieu | `build/<Projet>/<Tome>/chapters/*.md` |
| les illustrations du tome | **le style de dessin de l'œuvre** | `media/`, classées par `core/illustrations.py` |

**Le prompt n'a donc rien à inventer.** Et la règle qui gouverne ce lot est la même que celle de la
bible : *ce qui n'est pas dans l'œuvre n'entre pas dans le prompt.*

⚠ **Le prompt n'est que la moitié de la phase 1.** L'autre moitié est le **choix des images**
envoyées au modèle d'image comme références. C'est un choix, il se mesure, et il se relit : deux
recadrages de la bible plus une planche couleur de tête de volume ne donnent pas le même résultat
que trois portraits. `PLAN-25` L25.1 a mesuré le nombre et la nature du cadrage ; ce lot doit
**appliquer** ce verdict et laisser l'utilisateur le corriger image par image.

⚠ **Le périmètre reste « un personnage seul »** (décision du 2026-08-27). Ce lot construit un prompt
de **portrait / pose**, pas de scène. La tentation de faire glisser vers la scène complète parce que
« le texte le permet » est exactement le mélange de deux sources d'échec que la décision a écarté.
Une scène est un `PLAN-28`, s'il existe un jour.

---

## 2. Étape 0 — de quoi un prompt peut-il être fait, sur le corpus réel ?

Sur **3 personnages** ayant une bible validée, dépliez à la main ce qu'on peut écrire :

| Fragment du prompt | Sa source exacte | Présent ? |
|---|---|---|
| identité (attributs) | `bible.apparence` + `citations[]` | ? |
| genre | `glossaire.cibles.fr.genre` | ⚠ inconnu sur **87,7 %** des personnages avant `PLAN-23` |
| âge apparent | bible, ou déduit du texte | ? |
| tenue | bible, ou passage du chapitre | ? |
| cadrage | choisi par l'utilisateur, pas par le texte | — |
| style de dessin | à établir : voir 0.2 | ? |

**Publiez le tableau rempli pour les 3 personnages.** S'il est majoritairement vide, ce lot n'a pas
son matériau et c'est le `PLAN-23` qu'il faut prolonger, pas celui-ci qu'il faut écrire.

### 0.2 — Le style : mesuré, décrit, ou abandonné ?

« Cohérent avec l'œuvre » veut aussi dire *dans le même registre graphique*, et c'est la condition
qui répond à « ne pas produire un résultat trop loin des images précédentes ». Le matériau existe :
`PLAN-23` L23.7 a mesuré la **signature** du tome et retenu 2 à 5 **ancrages** validés à la main ;
`PLAN-25` L25.1 a donné une **échelle de style** et un verdict par image.

Trois approches, à départager par la mesure sur 10 images avec le juge du `PLAN-25` :

1. **Les mots** — injecter `bible.style.mots` (validé à la main) et les descripteurs lisibles de la
   signature (« palette désaturée, trait fin, aplats dominants ») dans le prompt. Coût nul, fidélité
   incertaine.
2. **Les ancrages en entrée du modèle** — passer une illustration d'ancrage **en plus** des
   références d'identité, sur le canal d'images (`PLAN-24` L24.2). Fidélité probablement meilleure,
   mais **deux risques mesurés séparément** : le décalque (plancher de nouveauté du `PLAN-25` L25.1)
   et la **contamination d'identité** — une ancre qui montre un autre personnage peut le faire
   apparaître dans l'image. Préférez des ancres **sans visage** (décor, objet, plan large) : les
   illustrations classées par `core/illustrations.py` en fournissent, et ce sont précisément celles
   qui ne servaient à rien pour l'identité.
3. **Le style par LoRA d'œuvre** — un adaptateur entraîné sur les illustrations du tome, non par
   personnage. Hors périmètre de ce lot ; il relève de la voie B du `PLAN-25` L25.3 et de sa décision
   écrite.

⚠ **« Ne pas traiter le style » n'est plus une option libre.** Elle ne se retient que si la mesure
de style du `PLAN-25` montre que les générations **restent dans l'échelle du tome sans rien faire** —
et alors c'est un résultat, avec son tableau. Sans cette mesure, ne pas traiter le style revient à
livrer de belles images étrangères à l'œuvre, ce qui est l'échec que la brique doit éviter.

### 0.3 — La forme du champ texte, et il faut la mesurer soi-même

Le modèle d'image ne reçoit pas un fichier : il reçoit des **arguments typés**, dont un seul est du
texte (README de série §4 ter). La question « JSON ou prose ? » ne porte donc que sur ce champ-là, et
deux conseils communautaires s'y contredisent, tous deux **sans dénominateur** :

| Forme à tester | Origine du conseil | Ce qu'elle prétend |
|---|---|---|
| **prose narrative** libre | discussion sur `Qwen-Image-Edit-2511` : « il utilise un LLM comme CLIP, parlez-lui en langage naturel » | la structure est inutile, le modèle comprend |
| **catégories étiquetées** — Subject, Pose, Clothing, Camera, Environment, Lighting, Mood — en 1 à 3 phrases | guide communautaire de `Qwen-Image-2512` | « +30 % de précision », prompt court > prompt long (« 31 mots battent 82 mots ») |
| **JSON sérialisé dans le champ texte** | l'hypothèse d'Alexandre | à traiter comme les deux autres : une hypothèse |

**Le protocole** : les mêmes 8 personnages, les mêmes références, la même graine, les trois formes,
jugées par le juge étalonné du `PLAN-25` étape 0.2 **et** par 10 comparaisons en aveugle. Publiez le
tableau des trois.

⚠ **Trois avertissements, et le troisième est le plus important.**

1. **Un JSON dans le champ texte n'est pas gratuit** : accolades, guillemets et clés consomment des
   tokens du budget de l'encodeur sans porter de structure que le modèle sache lire. S'il gagne quand
   même, c'est un résultat surprenant qui mérite d'être publié comme tel ; s'il perd, on aura la
   réponse chiffrée à une question qui revient sans arrêt.
2. **Le « +30 % » n'est pas une mesure**, c'est l'affirmation d'un article de blog sans corpus ni
   dénominateur. La règle des chiffres du dépôt s'applique : ne le recopiez nulle part comme un fait.
3. **Ce n'est pas là qu'est le gros du gain.** L'ordre de grandeur est : images de référence
   (identité) ≫ masques d'entités (position, forme) ≫ forme du texte. Cette étape ne doit pas coûter
   plus d'une journée, et **elle passe après** L26.0.

### 0.4 — Les canaux structurés : lesquels sont à portée ?

C'est ici que « plus de précision qu'un prompt » se joue vraiment. Inventoriez, avec licence
**vérifiée à la source primaire** et coût VRAM mesuré, les canaux que le moteur retenu au `PLAN-24`
expose réellement :

| Canal | Argument | Ce qu'il apporte au périmètre « un personnage seul » |
|---|---|---|
| images de référence | `edit_image` (`Qwen-Image-Edit-2511`, plusieurs images, désignées en prose : « image 1 », « la personne de l'image 2 ») | **l'identité** — c'est le canal principal, déjà traité par `PLAN-25` |
| entités + masques | `eligen_entity_prompts` + `eligen_entity_masks` (`Qwen-Image-EliGen-V2`, **Apache-2.0**, LoRA de 0,2 Md) | **la position et la forme** : cadrage voulu, place du personnage, zone laissée vide |
| image de contrôle | `blockwise_controlnet_inputs` (Canny/Depth), `context_image` (In-Context-Control-Union) | **la pose** — un croquis ou une pose extraite d'une illustration existante vaut cent adjectifs |
| couches | `Qwen-Image-Layered`, `Layered-Control` | sortie en calques : intéressant pour l'export PSD que le dépôt sait déjà écrire (`manga/psd.py`), **hors périmètre de ce lot** |

⚠ **Deux réserves à écrire, pas à contourner.** D'abord, la page qui documente ces variantes
**n'indique aucune licence variant par variant** : chacune se vérifie séparément avant usage, et le
dépôt a déjà cette jurisprudence (`docs/mesures/detecteurs-candidats-2026-08-26.md`, les poids de LaMa).
Ensuite, chaque canal supplémentaire est un poids de plus à charger dans 20 Go : un canal dont
l'apport n'est pas mesuré est un canal qu'on ne livre pas — **ou qu'on livre désarmé**.

**Périmètre raisonnable pour ce lot** : les images de référence (acquises) + **un** canal structuré
au plus, celui dont l'apport est mesuré. Les autres sont documentés comme candidats, non livrés.

---

## L26.0 — Choisir les images, et le justifier

Le LLM local reçoit les candidates — `references[]` validées de la bible, plus les illustrations du
tome classées par `core/illustrations.py` (`PLAN-23` L23.1) — et rend une **sélection ordonnée**,
avec un motif d'une ligne par image retenue et par image écartée.

Quatre règles :

0. **Une ancre de style au moins**, si l'étape 0.2 a retenu l'approche 2 : la sélection distingue
   `references` (identité, recadrages de personnage) et `ancrages_style` (registre graphique du
   tome). Ce sont **deux usages du même canal d'images**, et les mélanger sans le dire produit une
   image dont on ne sait pas ce qui a raté. Préférez une ancre **sans visage**, pour la raison
   d'identité de l'étape 0.2.
1. **Le nombre est plafonné** par le verdict de `PLAN-25` L25.1, pas par ce que le modèle voudrait.
2. **Une image générée n'est jamais candidate.** `PLAN-27` L27.3 rend le rebouclage impossible ; ici,
   la sélection ne lit que `references[]` et `media/`, jamais `images_generees[]`.
3. **Le motif est écrit dans `requete.yaml`.** Un utilisateur qui retire une image doit voir pourquoi
   elle avait été prise. Sans motif, la porte humaine se réduit à un clic de confiance.

⚠ **Coût VRAM :** juger 20 illustrations en vision sur `yume-27b` (`num_ctx: 32768`,
`decoupage.max_input_tokens` à 24 000) ne tient pas en un appel. Découpez par lots et **mesurez le
temps de la phase 1 complète** : si elle dure plus longtemps que la phase 2, c'est un fait à publier,
pas un détail.

## L26.1 — Le prompt est un fichier, pas une f-string

`langues/fr/prompts/illustration_portrait.md` et `langues/fr/prompts/illustration_style.md`.

**Interdit n° 6, mot pour mot** : les prompts sont du code source, ils vivent sous
`langues/<code>/prompts/`, et **l'en-tête de licence est à la fin du fichier, jamais au début** — un
modèle lit le haut du fichier comme une instruction. Ils se résolvent par
`core/langues.py:Pack.prompt(nom)` → `<racine du pack>/prompts/<nom>.md`. ⚠ **Ne les ajoutez pas à
`PROMPTS_REQUIS`** — les **huit** prompts dont l'absence fait échouer `_verifier_prompts` et
invaliderait le pack `langues/en`. Le modèle à suivre est `manga_relecteur.md` : livré dans les deux
packs, absent du tuple. Les neuf fichiers présents aujourd'hui sont `correcteur`, `glossariste`,
`manga_contexte`, `manga_onomatopees`, `manga_relecteur`, `manga_traducteur`, `mise_en_page`,
`terminologue`, `traducteur`.

⚠ **Ce sont deux natures de prompt différentes et il ne faut pas les confondre :**

- le prompt **du LLM local** (`yume-27b`), qui transforme la bible et un passage du chapitre en une
  description visuelle — c'est un prompt de langue, il va dans `langues/fr/prompts/` ;
- le prompt **du modèle d'image**, qui est le texte final envoyé au moteur. Il n'est pas propre au
  français (le modèle est multilingue mais mieux entraîné en anglais : à mesurer, en français
  contre anglais, sur 10 images), et sa **grammaire est celle du modèle**. Il vaut mieux un gabarit
  versionné dans `illustration/gabarits/` qu'un fichier de pack de langue.

`langues/` porte la voix d'un tome ; `illustration/gabarits/` porte la syntaxe d'un modèle. Séparez.

## L26.2 — La construction, déterministe dans sa charpente

`illustration/prompt.py` :

```python
def construire(personnage: str, bible, glossaire, *, cadrage: str,
               passage: str | None = None, style: str | None = None) -> Requete
```

- **charpente déterministe** : l'ordre des fragments, la ponctuation, le prompt négatif, les
  dimensions. Pure, sans LLM, **testable sans modèle**. C'est ce qui rend le résultat reproductible.
- **contenu cité** : chaque fragment d'apparence vient d'un champ de la bible qui porte sa
  `citations[]`. Un attribut sans citation n'entre pas — même règle que `PLAN-23` L23.4.
- **appel LLM facultatif** : il ne sert qu'à *reformuler* un passage du chapitre en description
  visuelle, jamais à ajouter un attribut. Un test doit prouver qu'un attribut absent de la bible ne
  peut pas apparaître dans la requête finale.

⚠ **Le prompt négatif compte autant que le prompt.** Il est le seul endroit où écrire ce que l'œuvre
n'est pas : pas de texte dans l'image (le modèle rend du texte, et un faux japonais ou un faux
français dans une illustration est un défaut visible), pas de filigrane, pas de cadre de case, pas de
bulle. Écrivez-le une fois, dans le gabarit, avec le motif de chaque terme.

## L26.2 bis — `requete.yaml`, le contrat de la porte humaine

C'est le seul artefact que l'utilisateur va vraiment lire. Il est donc **écrit pour être lu**, dans
le style de `config.yaml` : commenté, ordonné, tous les champs présents même vides.

⚠ **Pourquoi YAML pour l'humain et JSON pour la machine, et pas l'inverse.** `JSON` ne sait pas
porter un commentaire, et la porte humaine dépend entièrement de la lisibilité du fichier : la culture
du dépôt est celle de `config.yaml`, « un document » de 95 Ko de prose justifiée, et de
`glossaire.yaml`, qui écrit tous ses champs même vides « pour repérer d'un coup d'œil ce qui est
complétable ». Le **payload** envoyé au moteur, lui, est un dictionnaire typé sérialisé en JSON,
dérivé du YAML au moment de l'appel et **archivé tel quel dans le sidecar de provenance** — qui est
déjà un `.json` (`PLAN-24` L24.3). Deux formats, deux publics, un seul contenu : un test vérifie que
le YAML relu et le payload archivé décrivent la même requête.

```yaml
# Requête d'illustration — relisez, corrigez, puis passez `valide` à true.
# La phase 2 REFUSE de démarrer tant que `valide: false`.
valide: false
personnage: Tory Noelle
cadrage: buste
prompt: "…"                    # proposé par le LLM, corrigez librement
prompt_negatif: "…"            # gabarit ; retirer un terme est un choix, pas une faute
references:                     # IDENTITÉ — recadrages du personnage
- fichier: 'media/…_p12_x298.jpeg'
  motif: 'seul portrait de face validé dans la bible'
  retenue: true
- fichier: 'media/…_p61_x537.jpeg'
  motif: 'plan large, visage à 40 px — trop petit pour l identité'
  retenue: false
ancrages_style:                 # REGISTRE du tome — sans visage de préférence (étape 0.2)
- fichier: 'media/…_p1_x226.jpeg'
  motif: 'ancre validée : palette et trait du tome'
  retenue: true
attributs_sources:              # traçabilité : d'où vient chaque mot du prompt
- attribut: cheveux
  texte: "…"
  source: 'chapters/ch03.md'
graine: null                    # null = aléatoire, un entier = reproductible
nombre_images: 4

# Canaux STRUCTURÉS — présents seulement si l'étape 0.4 en a livré un, et désarmés sinon.
# Ce n'est pas du texte : ce sont des arguments typés du moteur. Ils portent la précision
# que le prompt ne peut pas porter (position, forme, pose).
canaux:
  entites: []                   # [{prompt: 'le personnage', masque: 'masques/…png'}] — EliGen
  image_de_controle: null       # croquis / pose / profondeur — ControlNet ou In-Context
```

⚠ **Deux champs que l'utilisateur doit pouvoir vider sans casser le run** : `graine` et
`attributs_sources`. Et **un champ qu'il ne doit pas pouvoir vider** : `references` — la phase 2 sans
référence retombe sur de la génération pure, ce que `PLAN-25` L25.2 refuse déjà. Le refus se dit ici
aussi, à la lecture du fichier, avec le motif nommé.

## L26.3 — La reproductibilité, jusqu'au bout

Toute `Requete` construite est **sérialisée dans le sidecar de provenance** du `PLAN-24` L24.3 :
prompt final, prompt négatif, graine, gabarit et sa version, empreinte de `bible.yaml`, empreinte de
`config.yaml`, version d'Angelith, révision du modèle.

Critère : **depuis un sidecar seul, on doit pouvoir régénérer la même image** (aux limites de
déterminisme mesurées en `PLAN-24` L24.5). Ajoutez la commande qui le fait :

```powershell
python run_illustration.py --rejouer <image>.provenance.json
```

C'est le même esprit que `git checkout <tag> -- langues/` pour reproduire la voix d'un tome : une
sortie dont on ne peut pas reconstruire l'entrée n'est pas traçable, et la traçabilité est une
exigence écrite du dossier de financement.

## L26.4 — Le budget, parce qu'un tome fait 20 illustrations et pas une

Le dépôt a une culture du plafond (`garde_fous.abandon_apres_timeouts_consecutifs`,
`decoupage.max_input_tokens`, budget unique rebranché en 2.2.0). Ce lot en a besoin :

- plafond d'images par run (défaut bas — proposition : 8), et le motif d'arrêt nommé ;
- plafond de tokens du passage envoyé au LLM (`decoupage.max_input_tokens` vaut 24 000, un chapitre entier
  ne passe pas — **découpez, ne tronquez pas silencieusement**) ;
- déchargement du LLM avant de charger le modèle d'image, **une seule fois pour tout le lot d'images**
  et non à chaque image : `core/power.py:ollama_unload` puis `ollama_load` à la fin. Mesurez le coût
  du va-et-vient si vous le faites autrement — sur 8 images, il peut dépasser le temps de génération.

## L26.5 — Le rapport

`RAPPORT.md` gagne, par illustration retenue : le personnage, le cadrage, la source de chaque
attribut (bible / texte / humain), la graine, et le verdict de ressemblance du `PLAN-25`. Un lecteur
doit pouvoir répondre à « d'où vient ce visage ? » sans ouvrir un `.json`.

---

## 3. Les critères de ce lot

1. Le tableau de l'étape 0 est publié pour 3 personnages, fragment par fragment, avec ses vides.
1 bis. La **sélection d'images** est produite avec un motif par image, retenue ou écartée, et le
   plafond appliqué est celui mesuré par `PLAN-25` L25.1 — pas un autre.
1 ter. `requete.yaml` est relisible et éditable à la main, `valide: false` par défaut, et la phase 2
   refuse de démarrer sans validation **et** sans référence retenue. Deux tests.
1 quater. Le temps de la **phase 1 complète** est mesuré et comparé à celui de la phase 2.
1 quinquies. Les **trois formes de champ texte** (prose, catégories étiquetées, JSON sérialisé) sont
   mesurées sur le même corpus, même graine, mêmes références, et le verdict est publié avec son
   dénominateur. Le « +30 % » de la source communautaire n'est recopié nulle part comme un fait.
1 sexies bis. L'approche de style retenue est celle que la mesure désigne, et si c'est « ne rien
   faire », le tableau de style du `PLAN-25` qui l'autorise est publié. La distinction
   `references` / `ancrages_style` existe dans `requete.yaml` et dans le payload.
1 sexies. Les **canaux structurés** sont inventoriés avec licence vérifiée à la source primaire et
   coût VRAM mesuré. **Un** canal au plus est livré, celui dont l'apport est mesuré ; les autres sont
   documentés comme candidats non livrés. Un canal non mesuré est livré **désarmé**.
1 septies. Un test vérifie que `requete.yaml` relu et le **payload JSON** archivé dans le sidecar
   décrivent la même requête.
2. Le style est traité par l'approche 1, 2, ou explicitement pas traité — avec le tableau de mesure
   sur 10 images qui justifie le choix.
3. `illustration/prompt.py:construire` est **pur** et testé sans LLM ni moteur.
4. Un test prouve qu'un attribut absent de `bible.yaml` ne peut pas entrer dans la requête finale.
5. Le prompt négatif est écrit dans le gabarit, chaque terme avec son motif.
6. `--rejouer <sidecar>` reproduit l'image, ou l'écart est mesuré et publié.
7. Français contre anglais est mesuré sur 10 images, et le défaut retenu est celui que la mesure
   désigne — pas celui qui semblait évident.
8. Les fichiers de prompt créés sont **nommés dans l'entrée de CHANGELOG**, en-tête de licence en
   fin de fichier, **hors** `PROMPTS_REQUIS`.
9. `ruff check .` passe ; `pytest -q -m "not modeles and not lent"` passe sans poids.
10. `docs/prompt-illustration-<date>.md` reprend ces critères un par un et dit ce que la mesure ne
    dit pas.

## 4. Ce que ce lot ne fait pas

- Pas de scène, pas de décor, pas de plusieurs personnages dans la même image.
- Pas d'interface : l'atelier est le `PLAN-27`.
- Il ne modifie **aucun** des neuf prompts existants. Si vous croyez devoir en toucher un, arrêtez :
  c'est un changement du caractère de la traduction, il n'appartient pas à ce lot.
