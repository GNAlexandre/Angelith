# PLAN 17 — Le traducteur cesse de travailler à l'aveugle

> **Lire `00-CONTEXTE-AGENT.md` d'abord.** Conventions, commandes, interdits et définition de
> « terminé » y sont, et ne sont pas répétés ici.
>
> **Nature attendue** — MINEUR. Ce lot réécrit `langues/*/prompts/manga_traducteur.md` et en
> ajoute un : la règle du CHANGELOG range toute réécriture de prompt qui change le caractère
> de la traduction dans les MINEURs et exige que l'entrée **nomme le fichier**.
>
> **Charge estimée** — 16 jours. Le plus long des six, et le seul dont une partie du résultat
> est incertaine (L17.9).
>
> **Prérequis** — le **lot 15** (externalisation des seize instructions en dur). Ce lot en
> ajoute quatre ou cinq : les écrire dans `langues/<code>/prompts/` dès le départ, jamais en
> f-string Python. Si le lot 15 n'est pas livré, faites-le d'abord — l'ordre inverse produit
> de la dette que le lot 15 devra reprendre.

---

## Pourquoi ce plan existe, et pourquoi il est en retard

Il est l'orphelin de la série. Les lots 10 à 14 ont livré le banc de mesure, rebranché sept
mécanismes inertes, activé la passe hors bulle, fait tomber les planches muettes de 188 à 153,
attrapé 33 doubles suspects et mesuré le webtoon de bout en bout. Tous portaient sur la
**détection**. Aucun n'a porté sur ce que le modèle **reçoit** pour traduire.

Le lot 11 (2.2.0) en a rebranché les tuyaux — la fiche de contexte atteint enfin le chemin par
défaut, le pluriel du prompt correspond aux trois planches réellement envoyées, le budget de
caractères est unique. Son entrée de changelog le dit elle-même : « **Ce lot ne gagne aucune
bulle** : il rend au traducteur le contexte qu'on avait déjà décidé de lui donner. » C'était le
bon périmètre. Mais « ce qu'on avait décidé de lui donner » est resté ce que c'était.

### Ce que le modèle reçoit aujourd'hui, exhaustivement

`_translate_page` construit sa liste `parts` dans cet ordre :

1. le glossaire sérialisé, plafonné à 4 000 tokens ;
2. **la fiche de contexte d'œuvre** — depuis 2.2.0, 174 à 261 tokens, médiane 219, soit
   +10,5 % de prefill sur le tome de référence ;
3. les 18 dernières répliques des 3 planches précédentes, en liste à tirets ;
4. la place disponible par bulle, en pixels, avec « dépasser force une police illisible » ;
5. la liste numérotée des bulles, plus une phrase donnant le sens de lecture.

### Ce qu'il ne reçoit pas

Vérifié par recherche sur `manga/`, `core/`, `langues/` et `config.yaml` : **aucune occurrence
de `type_bulle`, `recitatif`, `bulle_trop_courte`, `vision_ciblee`, `crop_case`.** `perte_mots`
n'existe que côté light novel (`core/quality.py`, `config.yaml`). Donc :

- **Qui parle.** Rien. Le modèle reçoit N répliques sans savoir combien de personnages sont
  dans la scène, ni si la réplique 4 répond à la 3 ou à la 1.
- **La structure de la planche.** Aucune frontière de case. `ocr._coupe_xy` **calcule** les
  gouttières, s'en sert pour trier, puis les jette.
- **Le type de bulle.** `BubbleRegion.kind` ne vaut que `"bulle"` ou `"onomatopee"` ;
  `text_detection.py:8-9` mesure `kind == "bulle"` **1 593 fois** sur les deux tomes. Rien ne
  distingue un dialogue d'une pensée, d'un récitatif ou d'un cri — alors que le français les
  écrit différemment, et que l'italique des pensées est déjà un acquis côté roman.
- **Une vérification de ce qui sort.** `quality_manga.MOTIFS` compte six prédicats, tous
  morphologiques : `vide`, `bulles_manquantes`, `japonais_residuel`, `repetition`,
  `emballement`, `bulle_trop_longue` — ce dernier bornant le ratio de longueur **par le haut
  seulement**. (⚠ `japonais_residuel` n'est pas « présence de CJK » : `libelle()` prend la
  langue en argument, précisément parce que « du japonais est resté dans la sortie » sur un
  chapitre anglais envoyait chercher un problème qui n'existait pas. Ne régressez pas là-dessus.) Une bulle japonaise de 40 caractères
  rendue par « Ouais. » les passe tous.
- **Un agent en aval.** `terminology.py:44` : « La brique manga n'a aucun agent en aval —
  l'étape suivante est un lettrage déterministe. » Le light novel a un `correcteur`
  (`config.yaml`, à `null`). Le manga n'en a pas la clé. Ce qui sort du traducteur est dessiné.

Et la pression du prompt est **structurellement** dans le sens de l'abrègement : un budget de
caractères par bulle, la formule « dépasser force une police illisible », et **aucune
contrepartie sur la fidélité**.

---

## Étape 0 — Mesurer avant de toucher au prompt

**Aucune ligne de code de ce lot avant que cette étape soit publiée et relue.** Toutes les
mesures ci-dessous se font sur les caches de `build/`, **sans un seul appel LLM**.

```powershell
python tools/banc.py --tous --traduction --markdown > docs/traduction-avant-<date>.md
python tools/banc.py --tous --markdown >> docs/traduction-avant-<date>.md
```

Puis, à écrire dans le même document, sur les 17 projets de `build/` :

| Mesure | Où la prendre |
|---|---|
| bulles vides dont la source portait du texte | `ocr.json` / `traduction.json`, alignés par position |
| bulles vides dont la source ne portait rien | idem — le `（）` de la page 8 n'a rien à traduire |
| distribution du ratio `len(rendu) / len(source)`, par langue source | idem |
| **et sa queue basse** : combien sous 0,35 | c'est le chiffre que L17.6 doit faire bouger |
| motifs `quality_manga` déclenchés, par motif | `qa.json` |
| rattrapages unitaires, et leur taux de rejet | `qa.json` |
| stratégie de rattachement : numérotée / positionnelle | `qa.json` |
| répartition de `kind` | `regions.json` |
| **nombre de groupes rendus par `_coupe_xy` par planche** | à instrumenter — c'est la matière de L17.1 |
| **combien de bulles ont une queue détectable** | à instrumenter — c'est la matière de L17.2 |

Les deux dernières lignes demandent d'écrire un peu de code de mesure. Écrivez-le sous
`tools/`, pas dans le pipeline, et faites-le **avant** de décider si L17.1 et L17.2 valent la
peine : si 80 % des planches rendent un seul groupe, L17.1 n'a presque rien à donner, et il
faut le savoir avant d'y passer trois jours.

⚠ Le corpus a **un seul volume à source latine**, qui est aussi le seul webtoon. Toute mesure
par langue source portera sur ce volume unique. Écrivez-le : c'est la même réserve que
`docs/mesures/webtoon-2026-08-26.md`, et elle vaut ici aussi.

---

## L17.1 — Donner la structure de la planche, elle est déjà calculée

**Le constat.** `ocr._coupe_xy` fait une coupe X-Y récursive par gouttières, et le raisonnement
est bon : « *panel-aware* sans jamais détecter les cases — les gouttières entre cases **sont**
les gouttières entre groupes de bulles ». Mais l'**arbre** de découpage est consommé pour
produire un ordre plat, puis jeté. Le modèle reçoit `1..N` et doit deviner que 1-2-3 sont dans
la même case et 4-5 dans la suivante.

**À faire.**

1. Faire remonter les groupes de `_coupe_xy` — la fonction est récursive, il s'agit de rendre
   l'arbre ou au minimum la partition de premier niveau, sans changer l'ordre produit. **Test
   d'iso-comportement obligatoire** : l'ordre de lecture de toutes les planches de `build/`
   doit être identique au bit. C'est le genre de refactor où une régression est invisible.
2. Les rendre visibles dans l'énoncé, sous un intertitre honnête :

   ```
   — Groupe 1 (rupture de mise en page) —
   1. …
   2. …
   — Groupe 2 —
   3. …
   ```

   **Ne pas écrire « case ».** Ce sont des groupes séparés par une gouttière, pas des cases
   détectées. Le prompt doit le dire, sinon le modèle inférera une précision qui n'existe pas.
   Le dépôt a déjà cette discipline : le prompt annonce la langue source et le sens de lecture
   au lieu de les laisser supposer.
3. **Quand le repli diagonal a servi, le dire.** `_coupe_xy` retombe sur un tri diagonal quand
   aucune gouttière n'existe — et ce repli donne un poids **égal** aux deux axes, ce qui ne
   correspond à aucune convention de lecture. Une planche triée par repli ne doit pas présenter
   un groupement dont on sait qu'il est incertain : ou bien on n'annonce pas de groupes, ou
   bien on dit qu'ils sont incertains.

**Ce que ça change.** Une réplique en tête de groupe est très souvent une nouvelle prise de
parole ou un changement de plan. Un modèle qui voit la rupture ne continue pas une phrase qui
n'existe pas. C'est aussi le seul moyen de rendre le « qui répond à qui » sans identification de
personnage.

**Critère.** Iso-ordre prouvé sur les 1 513 planches. Et la distribution du nombre de groupes
par planche publiée : si la médiane est 1, dites-le et concluez que l'étape n'apporte rien.

---

## L17.2 — La queue de bulle, que le code calcule pour la jeter

**Le constat, et c'est le plus frappant.** `geometry.width_profile` calcule la plage
**contiguë** contenant le centre, et sa docstring dit pourquoi : « la queue de la bulle
(l'appendice qui pointe vers le locuteur) est exclue ». La décision est juste pour son objet —
mesurer la largeur utile pour le lettrage. Mais cette phrase nomme elle-même ce qu'on jette :
la queue est **le seul signal graphique qui désigne le locuteur**.

**À faire.** L'extraire au lieu de la supprimer. La queue est l'appendice fin qui dépasse du
corps convexe du masque. Sa **direction** — angle du centroïde vers la pointe — pointe vers
celui qui parle. Aucun modèle, aucune dépendance : `geometry` a déjà l'érosion, la dilatation,
les composantes et `remplissage`.

De cette direction on tire, sans reconnaissance de personnages :

- deux bulles dont les queues pointent **vers le même endroit** sont le même locuteur ;
- deux bulles dont les queues pointent en sens **opposés** sont un échange ;
- une bulle **sans queue** n'est pas parlée — c'est l'entrée de L17.3.

**Sur l'état de l'art, et la conclusion à en tirer.** L'appariement texte↔locuteur est un
problème résolu en recherche : *The Manga Whisperer* (CVPR 2024) et les modèles Magi qui en
découlent font exactement cela. ⚠ **Ces poids sont « available for academic research purposes
only »**, donc inutilisables dans un projet redistribué sous AGPL, et le corpus Manga109 qui
les sous-tend a ses propres conditions. Le problème est donc faisable, et la voie géométrique
est la seule ouverte. **C'est un argument à écrire dans le document du lot**, pas un obstacle.

**Critère.** Sur un échantillon annoté à la main — 50 bulles suffisent, tirage figé et publié —
la direction de queue désigne le bon personnage combien de fois ? Publiez le taux. En dessous
de ~70 %, L17.4 ne doit pas être livré armé.

---

## L17.3 — Typer les bulles, avec une classe « indéterminé » généreuse

**Le constat.** Le champ existe, il est persisté, il est constant : 1 593 fois `"bulle"`.

**À faire.** Un classifieur **déterministe**, sans appel LLM, à partir de signaux déjà calculés :

| Type | Signature géométrique | Signal disponible |
|---|---|---|
| **récitatif** | rectangulaire, sans queue, souvent en coin de case | `remplissage` proche de 1,0 ; absence de queue (L17.2) |
| **pensée** | contour festonné | remplissage bas **et** contour lisse par morceaux |
| **cri** | contour en étoile | remplissage bas **et** contour anguleux |
| **dialogue** | le reste, avec une queue | L17.2 |
| **indéterminé** | tout ce qui n'est pas net | — |

`geometry.remplissage` établit les ordres de grandeur, et le dénominateur est écrit dans
`config.yaml` : les seuils viennent d'une mesure sur les **797 bulles** du tome de référence,
où « un ballon, même dentelé, remplit sa boîte (**médiane 0,89**) ». Pour les doubles, la même
source donne « les **vrais doubles sont entre 0,72 et 0,91** », les huit faux à 0,71 ou moins.

⚠ **Ne recopiez pas d'autres chiffres de remplissage sans les retrouver dans le dépôt.**
Un « 687 régions de plus de 20 000 px² » et un « 0,60-0,61 » circulent dans des documents de
planification antérieurs et ne se retrouvent nulle part dans le code — c'est exactement le cas
que `docs/chiffres-de-reference.md` existe pour trancher. Relevez la vôtre, avec son
dénominateur.

**Le cas de test existe déjà.** La planche synthétique du corpus annoté porte un
**récitatif rectangulaire** (`docs/procedures/banc-de-mesure.md`), et `quality_manga` mentionne déjà « une
bulle de récitatif contenant "1972…" ». Le vocabulaire est là ; c'est le champ qui manque.
Commencez par faire passer le classifieur sur le corpus synthétique, où la vérité est connue
par construction.

⚠ **La classe « indéterminé » n'est pas un aveu, c'est le cœur du dispositif.** Un type mal
deviné est pire qu'aucun type : une réplique criée passée en récitatif produit une phrase mal
placée, et le prompt aura demandé un registre narratif pour un cri. Ne typez que ce qui est
net, et publiez la part d'indéterminés — si elle dépasse 60 %, l'étape n'a pas trouvé son
critère et il faut le dire plutôt que de baisser les seuils.

**Ce que ça débloque, et c'est immédiat.** Le prompt peut demander l'italique pour une pensée,
un registre narratif pour un récitatif, une interjection courte pour un cri. C'est un gain
**typographique** sans risque, alors que la traduction elle-même est plus difficile à améliorer.

⚠ **Ne persistez pas le type dans `regions.json` sans réfléchir au cache.** Ajouter un champ à
`meta` est sans danger (les lecteurs anciens l'ignorent, `FORMAT_VERSION` ne bouge pas — c'est
exactement le raisonnement documenté pour le bloc de provenance). Mais un type **recalculé** à
chaque run et un type **lu du cache** doivent donner le même résultat, sinon un `--from rendu`
produira une autre planche. Écrivez le test.

---

## L17.4 — Un fil de dialogue à locuteurs stables

Assemblage de L17.1, L17.2 et L17.3 : à partir des groupes, des types et des directions de
queue, attribuer à chaque bulle d'une planche une **étiquette de locuteur locale** — A, B, C —
et la transmettre.

```
— Groupe 2 —
4. [A] …
5. [B] …
6. [A] …
```

**Trois précautions, non négociables.**

1. **Locale à la planche.** Suivre un personnage d'une planche à l'autre demande de la
   reconnaissance de personnages, que ce lot ne fait pas. Une étiquette locale est utile et
   honnête ; une étiquette globale fausse serait pire que rien.
2. **Le prompt dit ce que l'étiquette vaut** : « deux bulles marquées [A] sont *probablement*
   le même locuteur ».
3. **Aucune étiquette quand le signal est absent.** Une planche dont les queues sont illisibles
   n'en reçoit pas du tout. Le seuil vient de la mesure de L17.2.

**Ce que ça débloque.** C'est la condition du tutoiement cohérent, du genre des accords et des
pronoms. Le prompt système demande déjà de corriger « les pièges habituels des fantrads :
pronoms ambigus, sujets implicites, négations/ellipses mal rendues » — il demande donc au modèle
de lever une ambiguïté sans lui donner l'information qui la lève.

---

## L17.5 — Une vision ciblée, au lieu du tout-ou-rien

**Le constat.** `manga.mode_traduction` vaut `"texte"` par défaut, et son commentaire dit « à
réserver aux passages ambigus ». **Le code n'offre pas cette granularité** : en `"vision"`,
`_translate_page` joint la planche **entière** en PNG base64, pour **toutes** les planches du
tome. Il n'existe que deux sites d'appel LLM avec image dans tout le dépôt, tous deux pleine
page. Aucun crop de bulle ni de case n'est jamais envoyé.

Résultat : le coût maximal pour les 90 % de planches qui n'en ont pas besoin, donc un mode que
personne n'active.

**À faire.**

1. Un troisième mode, `"cible"` : premier passage textuel, **le diagnostic décide** d'une
   seconde tentative avec image. Les diagnostics existent et sont ordonnés — une planche dont le
   premier essai déclenche `bulles_manquantes`, `japonais_residuel` ou `vide` est exactement une
   planche ambiguë.
2. Joindre **le crop du groupe** (L17.1), pas la planche. Cinq à dix fois plus léger, et bien
   plus lisible pour un modèle vision parce que le sujet occupe le cadre.
3. **Correctif à faire même sans le reste** : en mode lot, `images` est une liste de N images
   pleine page et **rien dans le texte ne dit quelle image correspond à quelle planche**.
   L'appariement repose sur l'ordre implicite des pièces jointes. Nommez-les :
   « L'image jointe n° 2 est la planche 42 ».

**Le gain attendu est autant un gain de coût qu'un gain de qualité** : la vision devient
utilisable, donc utilisée, donc les cas ambigus sont traités par le seul mécanisme qui puisse
les traiter.

---

## L17.6 — Un garde-fou de perte de contenu, côté manga

**Le constat.** `quality_manga.MOTIFS` ne borne le ratio de longueur que **par le haut**
(`bulle_trop_longue`). `perte_mots` n'existe que côté light novel. Et le prompt pousse à
l'abrègement sans contrepartie.

**À faire.**

1. Un prédicat `bulle_trop_courte`, symétrique, ajouté au registre **ordonné** — donc il
   déclenche le retry, donc le rattrapage.
2. **Le ratio se calibre par langue source, sur le corpus, à l'étape 0.** Le japonais est
   dense : un ratio naïf produirait des faux positifs en masse. Vous avez 1 599 paires
   source/rendu sur les deux tomes de référence, plus les 15 autres projets de `build/` — la
   distribution existe, il n'y a qu'à la lire. ⚠ Et le seul volume à source latine est unique :
   le seuil latin sera donc calibré sur un échantillon d'un volume. Écrivez-le.
3. **Rééquilibrer le prompt** : la place disponible est une **contrainte**, pas un objectif.
   Quand une réplique fidèle ne tient pas, le bon comportement est de le **signaler** — le
   lettrage sait déjà le faire, `manga.typeset.debordement: "signaler"`, « on ne tronque
   JAMAIS » — et non de couper le sens.

**Critère.** Le nombre de bulles sous le ratio bas, avant/après. Et une inspection à l'œil de
**dix** d'entre elles, publiée : un prédicat de longueur qui déclenche sur de bonnes traductions
est un prédicat à jeter.

---

## L17.7 — Vérifier le registre a posteriori, sans LLM

La fiche de contexte dit « X vouvoie Y ». **Rien ne vérifie jamais que la traduction l'a
suivi** — et depuis 2.2.0 la fiche arrive enfin, donc la question devient mesurable.

C'est vérifiable lexicalement : les formes de deuxième personne du singulier et du pluriel sont
un ensemble fini, et le pack de langue est déjà l'endroit où vivent les règles d'accord
(`AccordFrancais` / `AccordNeutre`, acquis de la 2.0.0).

Un compteur par planche, un basculement signalé dans `RAPPORT.md`. **Aucun appel LLM**, donc
actif même quand `manga_contexte` ne l'est pas — le même patron que les dérives d'orthographe
T1/T2/T3, qui est un des bons mécanismes du projet.

Et c'est ce qui rend la fiche **évaluable** : aujourd'hui, même branchée, on ne sait pas si elle
sert. Ce chiffre-là est le seul qui puisse le dire.

⚠ Le vouvoiement dépend du pack de langue. Pour une cible sans distinction T/V, le compteur
doit être **absent**, pas à zéro — sinon `RAPPORT.md` affirme une conformité qui n'a pas de sens.

---

## L17.8 — Le retry manquant, et l'avertissement qui n'arrête rien

Deux défauts jumeaux du chemin par lots.

1. **Pas de retry de température.** `_translate_lot` fait un unique `agent.run`. La correction
   adaptative de température — seul remède documenté aux boucles dégénérées, avec
   `MOTIFS_PLUS_CHAUD` qui **relève** la température au lieu de la baisser — disparaît dès
   `lot.planches > 1`. Le repli par planche existe et est bien conçu, mais il rejoue la
   numérotation, et `config.yaml` documente que c'est justement ce qui échoue : « sur le Vol.1,
   les deux retries de page ont échoué comme leur premier essai ».
2. **`_verifier_num_ctx` et `place_disponible` avertissent et continuent.** Or Ollama « ne
   dégrade pas — il jette silencieusement plus de la moitié du prompt ». Un lot mal dimensionné
   produit des planches vides après un `warn` dans `perf.log`.

**Ce lot fait grossir le prompt** — groupes, types, locuteurs, budget rééquilibré. C'est
exactement le moment de transformer cet avertissement en **refus avec repli automatique sur un
lot plus petit**, et de compter les replis.

---

## L17.9 — Une passe de relecture, à évaluer et pas nécessairement à livrer

**Le constat.** Aucun agent en aval. Le roster manga a `manga_traducteur`, `terminologue`,
`glossariste`, `manga_onomatopees`, `manga_contexte`. Pas de correcteur.

**Ce qu'il ne faut surtout pas faire.** Un relecteur générique qui « améliore le style » est le
pire ajout possible : un appel par planche, un résultat non reproductible, et il défait autant
qu'il répare. La doctrine du projet doit tenir — **l'IA ne dessine jamais**, et un accord
incertain est **refusé** plutôt que produit.

**Ce qui a du sens** est un relecteur **à mandat étroit et nommé** : il voit la planche entière
(avec la fiche, les types et les locuteurs) uniquement pour vérifier un petit nombre de règles
explicites, et **il ne peut proposer une correction qu'en nommant la règle violée**. Une
correction sans règle nommée est **rejetée par le code**, pas par le modèle.

Règles candidates, toutes vérifiables :

- cohérence du tutoiement entre bulles d'un même couple de locuteurs (croise L17.4 et L17.7) ;
- accord de genre/nombre impossible à deviner bulle par bulle ;
- une réplique qui contredit celle à laquelle elle répond ;
- un terme du glossaire présent dans la source et absent du rendu.

**Il doit être livré désarmé** (`null`), comme le `correcteur` du light novel. Et **mesuré avant
d'être recommandé** : combien de corrections proposées, combien acceptées par le code, combien
jugées justes à la relecture humaine sur un échantillon publié. S'il ne gagne rien, écrivez-le
et laissez-le à `null`. **C'est un résultat, pas un échec de lot.**

---

## Ordre d'exécution — c'est une pile, pas une liste

1. **Étape 0** — mesurer. Publier. Attendre la relecture.
2. **L17.8** — indépendant, sans risque, et il protège tout le reste du lot.
3. **L17.1** — les groupes. Peu coûteux, prérequis de L17.4 et L17.5.
4. **L17.2** → **L17.3** → **L17.4** — la queue, puis les types, puis les étiquettes. Dans cet
   ordre : la queue est le signal, le type en dépend en partie, l'étiquette dépend des deux.
   **Chacune se mesure avant de passer à la suivante**, et chacune peut s'arrêter là.
5. **L17.5** — la vision ciblée, qui a besoin des boîtes de groupe.
6. **L17.6**, **L17.7** — les garde-fous, en dernier : ils mesurent ce que le reste a fait.
7. **L17.9** — le relecteur, à évaluer.

---

## Critères d'acceptation

Ils sont plus difficiles à formuler que pour un lot de détection, et c'est le vrai problème :
**une bulle mieux traduite ne se compte pas comme une bulle trouvée.** Reprenez-les un par un
dans le document du lot, avec leur verdict.

| # | Critère |
|---|---|
| 1 | Les huit mesures de l'étape 0 sont republiées après, dans le même tableau |
| 2 | Iso-ordre de lecture prouvé sur les 1 513 planches (L17.1) |
| 3 | Le taux de désignation correcte de la queue est publié sur un échantillon figé (L17.2) |
| 4 | La part de bulles « indéterminé » est publiée (L17.3) |
| 5 | Le seuil de `bulle_trop_courte` est calibré sur le corpus, et dix déclenchements sont inspectés à l'œil (L17.6) |
| 6 | Les basculements de registre sont comptés et publiés (L17.7) |
| 7 | Un échantillon **figé et publié** de 100 bulles, tiré des deux tomes de référence avec la graine écrite dans le dépôt, relu **à l'aveugle** dans les deux versions, sur trois questions fermées : le sens est-il juste, la longueur tient-elle, le registre est-il cohérent |
| 8 | `mode_traduction: "texte"` sans les nouvelles clés produit un résultat **inchangé** — c'est ce qui rend la comparaison possible |
| 9 | Chaque prompt touché est nommé dans le CHANGELOG, et `git checkout <tag> -- langues/` reproduit la voix |

⚠ Sur le critère 7 : **un juge unique qui est aussi l'auteur du changement n'est pas une
mesure.** Écrivez-le comme tel. C'est utile comme garde-fou, ce n'est pas un chiffre citable.

---

## Ce que ce lot ne fait pas

- Aucune reconnaissance de personnages, donc aucun suivi de locuteur entre planches.
- Aucune mémoire entre chapitres ni entre tomes. La fiche reste par tome, le glossaire reste le
  seul objet partagé — limite assumée : une mémoire inter-tomes demande une structure de données
  qui n'existe pas, et le glossaire fait déjà l'essentiel.
- Aucun relettrage d'onomatopée : `PLAN-21` et `PLAN-22`.
- **Il ne gagne aucune bulle.** C'était l'objet des lots 12 à 14 et du lot 16.
