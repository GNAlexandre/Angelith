# La bible visuelle — mesure du lot 23

- **Date de mesure** : 2026-08-29
- **Commit** : `613cfb2` (avant livraison du lot)
- **Version du dépôt** : 2.14.0
- **`config.yaml`** : sha256 `2f56020c1a03` — **inchangé par ce lot**
- **Corpus** : 15 dossiers `build/*/*/media/`, **446 fichiers** ; 14 `sources/*/glossaire.yaml`
  vivants, **326 personnages**
- **Modèle** : `yume-27b` (Ollama 0.33.1), `IQ4_XS`, 27,3 Md, projecteur CLIP 460,73 M

> Produit par `python tools/bible.py --tous --inventaire`, `--signature`, `--rapport`, et par
> les sondes de l'étape 0 reproduites ci-dessous. Aucun modèle d'image n'est chargé, aucun
> pixel d'une planche n'est écrit, aucun cache n'est touché.

⚠ **Les œuvres sont désignées neutrement** — `roman A` … `roman M`, `manga A`, `webtoon A` —
comme le veut `docs/PUBLICATION-ANGELITH.md` et comme `tools/verifier_arbre.py` le vérifie.
La correspondance vit dans le corpus local, pas ici.

**Ces étiquettes sont LOCALES à ce document.** Le `roman A` d'ici n'est pas celui d'un autre
compte rendu : le dépôt ne tient pas de registre global, et c'est délibéré — un registre
rendrait la désignation neutre inutile. **Seule exception : *Pride and Prejudice*, domaine
public**, et la seule œuvre dont une image aurait le droit de figurer dans un document de ce
dépôt.

---

## 0. Ce que la mesure ne dit pas

À lire avant les tableaux, parce que quatre de leurs chiffres sont plus fragiles qu'ils n'en
ont l'air.

1. **La qualité des attributs n'est pas mesurée, seulement leur traçabilité.** Ce lot garantit
   qu'un attribut de `bible.yaml` porte la phrase ou l'image d'où il vient. Il ne garantit pas
   qu'il soit vrai. Le seul juge est l'œil qui ouvre la citation — et la revue est faite pour
   que ce geste coûte trois secondes.
2. **L'ergonomie de `--revue` n'a pas été chronométrée sur un humain.** Le critère 4 du plan
   demande « 24 personnages en moins de 20 minutes chronométrées » ; un agent ne peut pas
   chronométrer une relecture humaine. Ce qui est mesuré est le **nombre de questions posées**
   (§6), qui en est le déterminant, pas le substitut.
3. **Une seule œuvre a été traitée de bout en bout** — roman D, 24 personnages, 2 tomes,
   42 illustrations. Les tableaux d'inventaire et de signature portent sur les 15 tomes ; les
   tableaux de proposition et de revue portent sur un seul projet. Le dire vaut mieux que de
   laisser une colonne remplie donner le change.
4. **La passe LLM n'est pas reproductible.** Trois passes texte identiques sur roman D, le même
   jour, la même configuration, ont donné **1, 25 et 36 refus** du code. Un chiffre de refus
   est donc un ordre de grandeur, pas une constante.

---

## 1. Étape 0.0 — les prémisses du plan, revérifiées

Le `PLAN-23` a été écrit le 2026-08-27. **Trois de ses chiffres ne tiennent plus deux jours
plus tard**, et c'est le corpus qui a bougé, pas le plan qui était faux.

| Mesure | Plan (2026-08-27) | Mesuré (2026-08-29) | Écart |
|---|---|---|---|
| Projets à `glossaire.yaml` vivant | 5 sur 17 | **14 sur 18** | +9 projets |
| Personnages déclarés | 171 | **326** | +155 |
| `role` vide | 171 / 171 — **100 %** | **326 / 326 — 100 %** | tient exactement |
| `genre` absent ou `'?'` | 150 / 171 — 87,7 % | **144 / 326 — 44,2 %** | −43,5 points |
| `description` vide | 0 / 171 | **0 / 326** | tient |
| Fichiers sous `build/*/*/media/` | 404, 13 dossiers | **446, 15 dossiers** | +42 |
| Part de *Pride and Prejudice* | 164 / 404 — 40,6 % | **164 / 446 — 36,8 %** | −3,8 points |

Détail par projet des personnages sans genre : manga A **106 / 114**, roman A 8 / 25, roman B 8 / 13, roman I 5 / 35, roman C 4 / 12,
roman D 4 / 24, roman J 3 / 27, roman K 3 / 17, roman F 2 / 7,
roman E 1 / 15. roman G, roman M et webtoon A sont
complets.

**Ce que ces écarts changent au plan.** Le constat de fond tient — `role` est toujours vide
sur 100 % des entrées, et il l'est maintenant sur 326 au lieu de 171. Le trou de genre, en
revanche, est **deux fois moins large en proportion**, et surtout il est **concentré** : à lui
seul, manga A porte **106 des 144** manques, soit **73,6 %**. Or ce projet est un
manga : son `build/` ne contient qu'un arbre `manga/` aux trois dossiers de planches **vides**,
sans `chapters/` ni `media/`. Le lot 23 n'a donc, pour lui, **aucune matière** — ni texte
traduit à lire, ni illustration à regarder. C'est le fait qui rend le critère 5 du plan
impossible, et il est traité au §7.

---

## 2. Étape 0.1 — le compte honnête des 446 fichiers

`python tools/bible.py --tous --inventaire`

| tome | fichiers | couverture | pleine_page | double_page | vignette | indeterminee | illisible | exploitables | en chapitre | tête de volume | non référencées |
|---|---|---|---|---|---|---|---|---|---|---|---|
| démo Vol.1 | 1 | 0 | 0 | 1 | 0 | 0 | 0 | 1 | 1 | 0 | 0 |
| roman D Vol.1 | 21 | 1 | 13 | 2 | 1 | 4 | 0 | 16 | 16 | 0 | 5 |
| roman D Vol.2 | 21 | 1 | 13 | 2 | 1 | 4 | 0 | 19 | 16 | 5 | 0 |
| roman E Vol.1 | 20 | 1 | 15 | 3 | 1 | 0 | 0 | 19 | 15 | 0 | 5 |
| Pride and Prejudice Vol.1 | 164 | 1 | 53 | 21 | 61 | 28 | 0 | 75 | 164 | 0 | 0 |
| roman F Vol.1 | 23 | 1 | 16 | 6 | 0 | 0 | 0 | 23 | 10 | 0 | 13 |
| roman G Vol.1 | 27 | 1 | 17 | 3 | 6 | 0 | 0 | 21 | 22 | 5 | 0 |
| roman H Vol.1 | 18 | 1 | 14 | 1 | 2 | 0 | 0 | 16 | 10 | 0 | 8 |
| roman I Vol.1 | 29 | 1 | 4 | 18 | 5 | 1 | 0 | 23 | 0 | 0 | 29 |
| roman I Vol.2 | 21 | 1 | 19 | 0 | 1 | 0 | 0 | 20 | 9 | 0 | 12 |
| roman I Vol.3 | 33 | 1 | 20 | 8 | 2 | 2 | 0 | 30 | 9 | 11 | 13 |
| roman I Vol.4 | 15 | 1 | 0 | 6 | 5 | 3 | 0 | 7 | 6 | 0 | 9 |
| roman K Vol.1 | 20 | 1 | 17 | 1 | 0 | 1 | 0 | 19 | 0 | 0 | 20 |
| roman L Vol.1 | 16 | 1 | 12 | 1 | 2 | 0 | 0 | 14 | 0 | 0 | 16 |
| roman M Vol.1 | 17 | 1 | 11 | 2 | 3 | 0 | 0 | 14 | 11 | 6 | 0 |
| **TOTAL (15 tomes)** | **446** | 14 | 224 | 75 | 90 | 43 | 0 | **317** | 289 | 27 | 130 |
| **TOTAL sans *Pride and Prejudice* (14)** | **282** | 13 | 171 | 54 | 29 | 15 | 0 | **242** | 125 | 27 | 130 |

**Le chiffre qui remplace 446 : 317 illustrations exploitables**, soit **71,1 %** des fichiers.
Sans *Pride and Prejudice*, **242 sur 282**, soit **85,8 %** — l'écart tient entièrement aux
**61 lettrines et culs-de-lampe de 100 × 110** de l'édition Hugh Thomson, qui tombent, à raison,
en `vignette`.

**Un critère du plan a été mesuré puis retiré, et c'est le résultat le plus utile de cette
étape.** L'étape 0.1 proposait de classer en vignette toute image de « moins de 3 couleurs
dominantes ». Appliqué aux 446 fichiers, ce critère range **48 images (10,8 %)** de surface
supérieure à 10 % de la médiane de leur tome parmi les logos : **6 des 27** de roman G,
**13 des 164** de *Pride and Prejudice*, 5 de roman I Vol.3, 5 de roman K. Ce sont des
planches au trait, noir sur blanc — deux teintes dominantes, et exactement le matériau de
référence le plus utile pour un tome monochrome. Le critère est retiré du classement ; le
compte de teintes reste **mesuré** parce que la signature de style s'en sert.
`tests/test_illustrations.py::test_une_illustration_au_trait_n_est_pas_une_vignette` empêche
son retour.

**Un second critère du plan a été remplacé.** « Couverture = premier marqueur du volume » échoue
sur deux tomes du corpus : sur roman D Vol.1 le premier marqueur est `p12`, une pleine page de
milieu de tome, parce que la vraie couverture `p1_x226` n'est citée par **aucun** marqueur ;
même défaut sur roman E. La règle retenue est **la première image dans l'ordre naturel
des noms de fichier qui soit portrait, non-vignette et d'au moins la surface médiane**. Elle
désigne une couverture sur **14 des 15 tomes** ; le quinzième (la démo, un seul fichier de
240 × 140 en paysage) n'en a pas, ce qui est correct.

⚠ **Ce que ce classement ne dit pas.** Il ne sait pas ce qu'une image représente. roman D Vol.1
p209 et p210 sont de vraies doubles pages, de ratio 1,25 et 1,23 — sous le seuil de 1,30 — et
tombent donc en `indeterminee`. C'est le comportement voulu : la classe généreuse absorbe le
doute au lieu de le trancher, comme le classifieur de type de bulle du `PLAN-17`.

---

## 3. Étape 0.2 — combien d'illustrations sont rattachables à un chapitre

Sur les 446 fichiers : **289 posés dans un chapitre**, **27 orphelins de tête de volume**,
**130 cités par aucun marqueur** (29,1 %).

Les 130 non référencés ne sont pas un défaut de rattachement, ils sont un défaut de **corpus** :

- **65** appartiennent à trois tomes qui n'ont **aucun rendu Markdown** — roman I Vol.1 (29),
  roman K Vol.1 (20), roman L Vol.1 (16) : les images ont été extraites, le texte n'a
  jamais été produit ;
- les **65 autres** sont répartis sur six tomes rendus, et ce sont, très majoritairement, les
  planches couleur de tête de volume et les couvertures — le cas que
  `pipeline/images.py:orphan_markers` documente déjà (« 12 illustrations sur 20 perdues »).

**Les 27 orphelines sont marquées `tete_de_volume` et retenues, pas jetées** : sur roman D
Vol.2, roman G, roman I Vol.3 et roman M, ce sont les planches couleur
d'ouverture — souvent la meilleure référence visuelle du tome.

---

## 4. Étape 0.3 — le LLM vision voit-il quelque chose ?

**`yume-27b` est bien vision-capable, et cette fois l'affirmation du dépôt est vraie.**
`ollama show yume-27b` :

```
  Capabilities        tools · thinking · completion · vision
  Projector           architecture clip · parameters 460.73M
                      embedding length 1152 · dimensions 5120
```

**Sonde sur 12 illustrations** (4 de *Pride and Prejudice*, domaine public ; 8 de roman D
Vol.1), redimensionnées à 1 024 px, sans le glossaire, avec pour seule consigne « décris ce que
tu vois ». Verdict porté **à la main**, en ouvrant chaque image :

| # | Illustration | Verdict | Ce qui a été vu, ou pas |
|---|---|---|---|
| 1 | P&P couverture | **exact** | reliure noir et or, paon sur un vase, titre, auteur **et illustrateur** lus |
| 2 | P&P i_030 | **exact** | 1 figure nue, paon, cartouche, « Chapter I. » |
| 3 | P&P i_031 | **exact** | 3 personnes, chapeaux hauts de forme, attelage — compte exact |
| 4 | P&P i_060 | partiel | **7 personnes sur 7**, la femme au piano exacte ; moustaches et vestes claires inventées ; réponse coupée au plafond de tokens |
| 5 | roman D p1 (couverture) | **exact** | cheveux argentés, yeux clairs, tenue militaire à croix, carnet |
| 6 | roman D p12 | partiel | les 2 personnes exactes, croix aux pattes de col comprises ; **une 3ᵉ silhouette inventée** dans un fond griffonné |
| 7 | roman D p27 | **exact** | 2 personnes, cheveux clairs, larmes, crasse, vestes militaires ; le **sparadrap au front** — un vrai `signe` — manqué |
| 8 | roman D p61 | partiel | 2 personnes, lame levée, cheveux au vent exacts ; « capuche ou bonnet » là où il y a un casque |
| 9 | roman D p66 | partiel | l'homme exact ; **1 personne annoncée pour 2** (les mains qui l'empoignent sont à un tiers) |
| 10 | roman D p75 | **exact** | homme en colère, femme en larmes, **et le cube de verre**, qui semblait une invention et n'en est pas une |
| 11 | roman D p116 | **faux** | premier plan donné pour un **homme** aux cheveux foncés en **chapeau de paille** et veste sombre ; le dessin montre une **jeune femme** aux cheveux clairs sous un **casque**, en tenue claire |
| 12 | roman D p209 | partiel | Gabak et Tory exacts, **noms lus sur la planche** ; « cheveux noirs courts » sous un casque qui n'en laisse rien voir |

**6 exactes, 5 partielles, 1 fausse. Descriptions inutilisables : 1 sur 12.**

**Verdict sur la porte de l'étape 0.3, et il tombe dans la zone grise du plan.** Le plan écrit
« ≥ 8 sur 12 correctes → L23.3 faisable ; < 6 → arrêter L23.3 ». Selon la lecture, on est à
**11 sur 12** (exactes + partielles) ou à **6 sur 12** (exactes seules) — c'est-à-dire au-dessus
du plancher d'arrêt et en dessous du seuil de confort. **Décision prise, et écrite ici : L23.3
est livrée, et livrée sans autorité.** Sa sortie ne va que dans `bible.propositions.yaml`, avec
`confiance: 'llm'`, et rien n'entre dans `bible.yaml` sans un `o` humain. C'est ce que le plan
imposait déjà ; la mesure dit pourquoi c'était la bonne consigne.

⚠ **Deux observations que le score ne porte pas, et qui comptent davantage.**

- **La seule description fausse porte sur le genre.** Le n° 11 sexe un personnage à l'inverse
  du dessin. Si un jour l'illustration devait alimenter le champ `genre` du glossaire — celui
  qui commande les accords français — ce serait exactement l'erreur à ne pas propager. C'est
  une raison de plus pour que `--ecrire-genre` reste un geste explicite avec la preuve sous
  les yeux.
- **Le modèle LIT la planche autant qu'il la reconnaît.** Sur le n° 12, il restitue « Gabak »
  et « Tory » parce que les deux noms sont **étiquetés en clair sur l'image**. Compter cela
  comme de la reconnaissance de personnage surestimerait ce que la passe sait faire sur une
  planche sans étiquette.

**Coût.** Sonde exploratoire : **99,9 s pour 12 images, soit 8,3 s/image** (la couverture
ornementale de *Pride and Prejudice*, la plus dense, à 32,3 s). En production, avec le prompt
court de `bible_apparence.md`, la passe complète de roman D — **241 passages de texte en
10 lots + 35 illustrations** — tient en **2 min 04 s** de bout en bout.

---

## 5. L23.7 — la signature de style, par tome

`python tools/bible.py --tous --signature`

| tome | échantillon | couleur | saturation | contraste | densité trait | part aplats | palette (3 premières) |
|---|---|---|---|---|---|---|---|
| démo Vol.1 | 1 | oui | 0.55 | 0 | 0 | 0 | #5070d0 100 % |
| roman D Vol.1 | 16 | non | 0.07 | 0.24 | 0.27 | 0.37 | #f0f0f0 47 %, #d0d0d0 13 %, #b0b0b0 6 % |
| roman D Vol.2 | 19 | non | 0.12 | 0.23 | 0.17 | 0.46 | #f0f0f0 40 %, #d0d0d0 7 %, #303030 7 % |
| roman E Vol.1 | 19 | non | 0.09 | 0.26 | 0.17 | 0.46 | #f0f0f0 26 %, #101010 9 %, #505050 9 % |
| Pride and Prejudice Vol.1 | 75 | non | 0 | 0.21 | 0.31 | 0.48 | #f0f0f0 70 %, #d0d0d0 9 %, #b0b0b0 7 % |
| roman F Vol.1 | 23 | non | 0.12 | 0.22 | 0.23 | 0.47 | #f0f0f0 40 %, #d0d0d0 9 %, #101010 7 % |
| roman G Vol.1 | 21 | non | 0.06 | 0.17 | 0.20 | 0.35 | #f0f0f0 39 %, #b0b0b0 11 %, #d0d0d0 10 % |
| roman H Vol.1 | 16 | non | 0.15 | 0.25 | 0.21 | 0.42 | #101010 19 %, #f0f0f0 16 %, #707070 11 % |
| roman I Vol.1 | 23 | **oui** | 0.13 | 0.24 | 0.15 | 0.48 | #f0f0f0 29 %, #101010 7 %, #d0d0d0 7 % |
| roman I Vol.2 | 20 | non | 0.07 | 0.22 | 0.15 | 0.48 | #f0f0f0 33 %, #d0d0d0 12 %, #b0b0b0 10 % |
| roman I Vol.3 | 30 | non | 0.05 | 0.19 | 0.13 | 0.47 | #f0f0f0 27 %, #d0d0d0 13 %, #505050 10 % |
| roman I Vol.4 | **7** | non | 0.01 | 0.22 | 0.12 | 0.49 | #f0f0f0 33 %, #d0d0d0 13 %, #b0b0b0 12 % |
| roman K Vol.1 | 19 | non | 0.05 | 0.25 | 0.19 | 0.45 | #f0f0f0 34 %, #909090 9 %, #707070 9 % |
| roman L Vol.1 | 14 | non | 0.07 | 0.24 | 0.20 | 0.47 | #f0f0f0 39 %, #d0d0d0 15 %, #b0b0b0 6 % |
| roman M Vol.1 | 14 | non | 0.10 | 0.21 | 0.16 | 0.30 | #f0f0f0 14 %, #909090 13 %, #707070 11 % |

### Écart de signature entre tomes consécutifs d'une même œuvre

| œuvre | tomes | saturation | contraste | densité trait | part aplats | **moyenne** | échantillons |
|---|---|---|---|---|---|---|---|
| roman D | Vol.1 ↔ Vol.2 | 0.0555 | 0.0093 | **0.0966** | **0.0953** | **0.0642** | 16, 19 |
| roman I | Vol.1 ↔ Vol.2 | 0.0678 | 0.0239 | 0.0022 | 0.0043 | 0.0245 | 23, 20 |
| roman I | Vol.2 ↔ Vol.3 | 0.0151 | 0.0264 | 0.0133 | 0.0048 | **0.0149** | 20, 30 |
| roman I | Vol.3 ↔ Vol.4 | 0.0365 | 0.0294 | 0.0107 | 0.0161 | 0.0232 | 30, 7 |

**Ce que ces écarts disent, et ce qu'ils ne disent pas.**

- Une signature **par œuvre** n'est pas absurde sur ce corpus : les quatre écarts moyens tiennent
  entre 0,015 et 0,065, sans valeur aberrante.
- Mais **l'écart roman D Vol.1 ↔ Vol.2 est 4,3 fois celui de roman I Vol.2 ↔ Vol.3**, et il
  porte sur les deux descripteurs de trait : 0,27 → 0,17 de densité, 0,37 → 0,46 d'aplats. Deux
  tomes de la même série, chez le même illustrateur, ne sont donc pas interchangeables. Une
  signature **par tome** reste le bon grain ; c'est celle que `bible.yaml` écrit.
- **`roman I` Vol.1 est le seul tome « couleur » du corpus**, et ses trois suites sont en
  niveaux de gris. L'écart de régime de couleur est signalé à part parce qu'il ne se moyenne
  pas : une planche N&B et une planche couleur ne se comparent pas descripteur par descripteur.

⚠ **`roman I` Vol.4 a un échantillon de 7.** C'est la réserve que le champ `echantillon` existe
pour rendre visible : sa signature vaut ce que valent sept images, et l'écrire sans son
dénominateur en ferait une impression. La démo, à un échantillon de 1, est un cas dégénéré
laissé tel quel plutôt que masqué.

⚠ **Cet écart n'a pas encore d'échelle.** Il dit que deux tomes diffèrent de 0,0966 sur la
densité de trait ; il ne dit pas si 0,0966 est beaucoup. **Ce lot ne fait rien de la
signature** : il la mesure et l'écrit. Lui donner une échelle est l'étape 0.2 du `PLAN-25`, la
consommer est `PLAN-26` L26.0.

---

## 6. L23.3 à L23.6 — la chaîne complète, sur roman D

### 6.1 La passe lexicale, et le défaut qu'elle a d'abord eu

`core/bible_texte.py` croise un lexique d'apparence avec le nom du personnage et ses variantes,
dans une fenêtre de deux phrases. Première écriture : appariement par **sous-chaîne**. Résultat
sur le corpus : **13 838 passages candidats**, dont roman D **1 565**.

**80,3 % de ces candidats étaient faux, et tous de la même famille** : « ans » s'appariait à
*dans*, *sans*, *enfants* ; « regard » à *regarder*, *regardait*. Sur roman D seul,
**1 257 des 1 565** passages, tous rangés sous `age_apparent`. Correctif : appariement **ancré
aux frontières de mot**, racines longues autorisées à deux lettres de suffixe, racines courtes
et ambiguës écrites en mots exacts, et « regard » retiré — un regard n'est pas un attribut
dessinable.

| projet | personnages avec ≥ 1 passage | passages | par attribut |
|---|---|---|---|
| roman D | **20 / 24** | 241 | yeux 111, age 88, tenue 31, signes 7, cheveux 4 |
| roman E | **15 / 15** | 64 | yeux 25, tenue 18, age 10, cheveux 9, signes 2 |
| roman F | **7 / 7** | 143 | yeux 73, age 35, tenue 23, cheveux 12 |
| roman G | **26 / 27** | 1 064 | yeux 520, cheveux 290, tenue 126, age 94, signes 34 |
| roman I | **27 / 35** | 995 | yeux 358, age 318, tenue 158, cheveux 127, signes 34 |
| roman M | **9 / 9** | 156 | age 69, yeux 64, tenue 11, cheveux 8, signes 4 |
| roman A, roman B, roman C, webtoon A, manga A, roman K | **0** | 0 | — |
| **TOTAL** | **104 / 299** | **2 663** | — |

**Le dénominateur qui compte n'est pas 299, il est 117.** Les six projets à zéro passage n'ont
aucun `chapters/` : ce sont des projets **manga**, et roman K, dont seules les images ont
été extraites. Sur les **117 personnages des projets qui portent du texte traduit**, la passe
lexicale en atteint **104, soit 88,9 %**.

### 6.2 Ce que le code refuse au modèle

Passe complète sur roman D (241 passages en 10 lots + 35 illustrations), **2 min 04 s** :

| grandeur | valeur |
|---|---|
| attributs proposés | **82** |
| refusés par le code | **29** — dont `passage_invalide` 25, `nom_inconnu` 4 |
| appels vision | **35** |
| **abstentions vision** | **26 / 35 — 74,3 %** |

**Le cas qui justifie le garde-fou n° 2 à lui seul.** Sur un lot de 25 passages, `yume-27b`
est parti en boucle : la ligne `Gomuji | age_apparent | dix-huit ans` répétée avec un numéro
de passage incrémenté **de 26 à 50** — au-delà du lot fourni. Sans le contrôle de plage, un
attribut serait entré **25 fois** dans la bible avec **25 citations fabriquées**. Le contrôle
en a refusé 25 sur 25.
`tests/test_bible.py::test_la_boucle_du_modele_est_entierement_refusee` fige ce cas.

**L'abstention à 74,3 % est le bon sens de lecture.** Le plan avertit qu'« une abstention basse
est suspecte » : 26 illustrations sur 35 n'ont produit aucun attribut de certitude déclarée.
Sur des planches d'action, de décor ou de personnage secondaire non nommé au glossaire, c'est
la réponse correcte. Les 4 `nom_inconnu` sont des noms que le modèle a inventés ou lus sur la
planche sans qu'ils existent au glossaire : **rejetés, pas ajoutés**.

⚠ **Le choix de l'agent change le résultat, et il a fallu le mesurer.** Avec `terminologue`
(raisonnement activé), **8 des 10 lots** de la passe texte sortent « génération coupée net au
plafond max_tokens » — le budget entier part dans le `<think>`. La passe emploie donc
`mise_en_page`, le seul agent du roster livré avec le raisonnement coupé. Relever un attribut
n'est pas un problème de raisonnement, c'est une lecture.

### 6.3 La revue, et la `bible.yaml` qui en sort

`python tools/bible.py "roman D" --revue` — **11 personnages proposés sur 24**, 38 questions
posées, `sources/roman D/bible.yaml` écrit :

| personnage | attributs | références | citations |
|---|---|---|---|
| Tory Noelle | 5 / 5 | 7 | 32 |
| Gale | 5 / 5 | 1 | 7 |
| Gomuji | 4 / 5 | 0 | 21 |
| Kayle | 4 / 5 | 1 | 4 |
| Isaac Fenn, Aria | 3 / 5 | 1, 0 | 4, 3 |
| Allen, La nonne | 2 / 5 | 0 | 4, 2 |
| Salsa, Major Lenvil, Bear | 1 / 5 | 0 | 2, 1, 2 |

Plus le bloc `style:` : **signature sur un échantillon de 16**, et **3 ancrages validés à la
main** parmi les pleines pages les plus proches du centre de la distribution du tome
(écarts 0,393 / 0,417 / 0,433 sur 4 descripteurs).

⚠ **Le temps de revue n'est pas chronométré ici.** Ce qui est mesuré : **38 questions pour
11 personnages**, soit 3,5 par personnage. Extrapolé à un projet de 24 personnages entièrement
proposés, ~80 questions ; à dix secondes par question, ~13 minutes — **sous les 20 minutes du
critère 4, mais par extrapolation, pas par chronomètre**. Le raccourci `O` (« tout accepter
pour ce personnage ») réduit la revue d'un personnage à une seule frappe quand ses attributs
sont bons ; c'est lui qui décide de l'ergonomie réelle, et seul un humain peut le dire.

### 6.4 Le banc

`python tools/bible.py --tous --rapport`

| projet | personnages | couverture de référence | couverture d'attributs | genre avant | genre après | illustrations exploitées | abstentions LLM |
|---|---|---|---|---|---|---|---|
| roman D | 24 | **4 / 24** | **6 / 24** | 20 / 24 | 20 / 24 | 35 / 42 | **26 / 35** |
| roman E | 15 | 0 / 15 | 0 / 15 | 14 / 15 | 14 / 15 | 19 / 20 | — |
| roman F | 7 | 0 / 7 | 0 / 7 | 5 / 7 | 5 / 7 | 23 / 23 | — |
| roman G | 27 | 0 / 27 | 0 / 27 | 27 / 27 | 27 / 27 | 21 / 27 | — |
| roman I | 35 | 0 / 35 | 0 / 35 | 30 / 35 | 30 / 35 | 80 / 98 | — |
| roman K | 17 | 0 / 17 | 0 / 17 | 14 / 17 | 14 / 17 | 19 / 20 | — |
| roman M | 9 | 0 / 9 | 0 / 9 | 9 / 9 | 9 / 9 | 14 / 17 | — |
| manga A | 114 | 0 / 114 | 0 / 114 | **8 / 114** | 8 / 114 | — | — |
| roman A | 25 | 0 / 25 | 0 / 25 | 17 / 25 | 17 / 25 | — | — |
| roman B | 13 | 0 / 13 | 0 / 13 | 5 / 13 | 5 / 13 | — | — |
| roman C | 12 | 0 / 12 | 0 / 12 | 8 / 12 | 8 / 12 | — | — |
| webtoon A | 1 | 0 / 1 | 0 / 1 | 1 / 1 | 1 / 1 | — | — |
| Pride and Prejudice | 0 | — | — | — | — | 75 / 164 | — |
| démo, roman H, roman L | 0 | — | — | — | — | 1/1, 16/18, 14/16 | — |

Les zéros sont réels : **une seule œuvre a été traitée**. Le banc est là pour que la suivante
se mesure contre celle-ci.

---

## 7. L23.5 — le genre, et le mur que le corpus lui oppose

C'est le gain qui devait justifier le lot à lui seul. Il est livré, il est mesuré, **et le
critère chiffré du plan est hors d'atteinte sur ce corpus**.

### 7.1 L'indice de genre est déterministe, et sa précision se mesure

`core/bible_texte.indices_de_genre` relève, **ancrés sur le nom du personnage**, quatre familles
de motifs par genre : civilité accolée au nom (*Mademoiselle X*, *Messire X*), attribut avec
article (*X était une soldate*), pronom réfléchi (*X elle-même*), et apposition possessive.
Deux occurrences minimum, et deux d'écart avec le genre concurrent.

**Le corpus fournit sa propre vérité terrain** : 105 personnages, dans les projets à texte,
portent **déjà** un genre déclaré au glossaire. L'indice y est confronté :

| | valeur |
|---|---|
| personnages à genre déclaré, dans un projet à texte | **105** |
| indice **concordant** avec la déclaration | **26** |
| indice **contredisant** la déclaration | **0** |
| indice muet | 79 |
| **précision** | **26 / 26 — 100 %** |
| **rappel** | **26 / 105 — 24,8 %** |

Zéro contradiction sur 26 relevés. Un rappel d'un quart : l'indice est **silencieux quatre fois
sur cinq**, et c'est le compromis voulu. Le champ `genre` commande les accords français ; un
motif large aurait un meilleur rappel et une précision inconnue, et produirait « il est
arrivée » sur un tome entier.

### 7.2 Pourquoi le critère « 30 des 150 » ne peut pas être tenu

| | valeur |
|---|---|
| personnages sans genre, tout le corpus | **144** |
| dont dans un projet **sans** texte traduit **ni** illustration extraite | **129 — 89,6 %** |
| **plafond atteignable par ce lot** | **15** |
| dont l'indice déterministe propose déjà un genre | **4** |

**106 des 144 manques sont dans manga A**, dont le `build/` ne contient qu'un arbre
`manga/` aux dossiers de planches vides : ni `chapters/` à lire, ni `media/` à regarder. Les
23 autres manques hors d'atteinte sont dans roman A, roman B,
roman C et roman J, mêmes causes.

**Le critère 5 du plan demande 30 résolutions ; le corpus en autorise au maximum 15.** Ce n'est
pas un échec de la brique, c'est une propriété du corpus au 2026-08-29, et elle était invisible
au moment où le plan a été écrit — parce que le plan comptait 5 projets vivants là où il y en a
14, et n'avait pas remarqué que le plus gros porteur de manques n'a aucune matière.

**Aucun genre n'a été écrit dans un `glossaire.yaml`.** `--ecrire-genre` n'a pas été employé :
la décision d'écrire dans le seul champ que le traducteur lit — donc de changer les accords de
tout tome relancé — appartient à Alexandre, pas à l'agent qui livre l'outil. L'outil met
l'indice, ses exemples de phrase et les illustrations de référence sous l'œil, et attend un
`f`, un `m` ou un `?`.

---

## 8. Une règle de couche du dépôt a contredit le plan, et c'est la règle qui a gagné

Le `PLAN-23` L23.1 demande `core/illustrations.py` **et** la réutilisation de
`pipeline.images.manifest_for_chapter` (« n'écrivez pas un second parseur de marqueurs »). Les
deux ensemble sont impossibles : `tests/test_core_cli.py::test_le_socle_nimporte_ni_les_briques_ni_les_cli`
et `tests/test_core_alias.py::test_le_socle_ne_depend_pas_du_pipeline` interdisent à `core/`
d'importer `pipeline/`, et ils ont échoué à la première exécution de la suite complète.

Réécrire un second analyseur aurait satisfait la règle de couche en violant l'instruction du
plan — et deux analyseurs du même format divergent le jour où le format bouge. La sortie
retenue est la troisième : **le contrat du marqueur `<!-- IMG: … -->` est un contrat partagé, et
il descend dans le socle**, `core/marqueurs.py`. `pipeline/extract.py` et `pipeline/images.py`
réexportent `IMG_MARKER`, `make_marker`, `split_marker`, `strip_images`, `orphan_markers` et
`manifest_for_chapter` sous leurs noms d'origine.

**Neutre pour les appelants, et prouvé** : `tests/test_images.py::test_les_noms_reexportes_sont_les_MEMES_objets_que_ceux_du_socle`
vérifie l'**identité d'objet**, comme le lot 2.1 pour les alias `pipeline.x` → `core.x` — seule
propriété qui rende un déplacement neutre pour le monkeypatching du dépôt. Une copie de
l'expression du marqueur a disparu de `pipeline/images.py` au passage.

---

## 9. Les neuf critères du plan, un par un

| # | Critère | Verdict |
|---|---|---|
| 1 | `core/illustrations.py` classe les fichiers de tous les dossiers `media/`, répartition publiée par tome, **avec et sans** *Pride and Prejudice* | ✅ **tenu** — §2. 446 fichiers et 15 dossiers, non 404 et 13 : le corpus a bougé, l'écart est publié au §1 |
| 2 | `bible.yaml` se charge et se sauve sans perdre un champ manuel ; `verifier_coherence` refuse un nom hors glossaire ; `glossaire.yaml` **inchangé octet pour octet** | ✅ **tenu** — tests `test_un_aller_retour_disque_preserve_un_champ_rempli_a_la_main`, `test_un_nom_absent_du_glossaire_est_refuse`. Aucun `glossaire.yaml` n'a été réécrit : les 14 mtimes sont antérieurs au lot |
| 3 | Aucun attribut sans `citations[]` dans une `bible.yaml`. Un test le prouve | ✅ **tenu** — `test_un_attribut_sans_citation_n_est_PAS_ecrit` vérifie en plus que la valeur purgée **a disparu du fichier**, pas seulement de l'objet |
| 4 | `--revue` traite 24 personnages en moins de 20 minutes **chronométrées** | ⚠ **partiel** — l'outil existe et fonctionne ; 38 questions pour 11 personnages. La chronométrie humaine n'est pas mesurable par un agent (§6.3) |
| 5 | Genre résolu sur au moins **30 des 150** sans genre, ou explication | ❌ **non tenu, et expliqué** — le plafond atteignable est **15**, parce que **129 des 144** manques sont dans des projets sans texte ni image (§7.2). L'outil est livré, mesuré à **100 % de précision sur 26 relevés**, et aucun genre n'a été écrit sans décision humaine |
| 6 | Aucune image, aucun recadrage, aucun nom d'œuvre dans un fichier suivi par git | ✅ **tenu** — `git check-ignore -v` confirme `sources/` pour `bible.yaml` et `bible.propositions.yaml` ; `git status --porcelain` ne liste que du code, des tests, des prompts et ce document |
| 7 | `ruff check .` passe, `pytest -q -m "not modeles and not lent"` passe, tests neufs pour L23.1, L23.2 et L23.4 | ✅ **tenu** — **3 284 passés, 3 ignorés, 57 désélectionnés** ; 3 344 collectés. **65 tests neufs** — 63 dans `test_illustrations.py` et `test_bible.py`, 2 dans `test_images.py` |
| 8 | Bloc `style:` par tome mesuré : signature **avec échantillon**, 2 à 5 ancrages **validés à la main**, écart entre tomes publié | ✅ **tenu** — §5 pour les 15 tomes ; `sources/roman D/bible.yaml` porte 3 ancrages validés et une signature d'échantillon 16 |
| 9 | Le document publie **ce que la mesure ne dit pas** | ✅ **tenu** — §0, et les réserves signalées ⚠ à chaque section |

**Sept tenus, un partiel, un non tenu documenté.**

---

## 10. Ce que le lot ne fait pas, et n'a pas commencé à faire

- Aucune image générée, aucun modèle génératif importé, aucune dépendance ajoutée
  (`requirements*.txt` inchangés — Pillow et numpy étaient déjà là).
- Aucune détection de visage, aucun recadrage automatique. Le champ `recadrage` existe et reste
  vide : il se remplit à la main. Pas d'OpenCV.
- `manga/checkpoints.py:STAGES`, `FORMAT_VERSION` et `.checkpoints/` ne sont pas touchés. La
  bible n'est pas une étape de pipeline : elle n'invalide rien.
- `config.yaml` n'a **aucune clé nouvelle**, armée ou non. Rien du chemin nominal ne lit la
  bible, et une clé que rien ne lit encombrerait un fichier qui est un document.
- La bible n'entre pas dans le prompt du traducteur. Le seul champ qui peut traverser vers la
  traduction est `genre`, par `--ecrire-genre`, et il ne l'a pas fait.
- `bible_apparence.md` est livré dans les deux packs et **absent de `core/langues.py:PROMPTS_REQUIS`**,
  comme `manga_relecteur.md` : y ajouter un nom rendrait invalide, au démarrage d'un run de
  traduction, tout pack tiers écrit avant ce lot. Son absence vaut refus explicite de la
  brique — jamais un repli silencieux vers le français.
