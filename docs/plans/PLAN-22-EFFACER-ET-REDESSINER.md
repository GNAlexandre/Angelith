# PLAN 22 — Effacer et redessiner : le relettrage du texte hors bulle

> **Lire `00-CONTEXTE-AGENT.md` d'abord.**
>
> **Nature attendue** — MINEUR **si** le mode est opt-in et le défaut inchangé. MAJEUR si `sfx`
> entre dans le graphe d'invalidation (voir L22.6) — ce qui périmerait **tous** les rendus
> existants. Tranchez-le explicitement, ne le découvrez pas.
>
> **Charge estimée** — 18 jours, dont une part de R&D au résultat incertain. C'est le seul plan
> de la série qui peut légitimement se conclure par « on ne le fait pas », et cette conclusion
> doit être publiée comme un résultat.
>
> **⚠ Prérequis absolu : `PLAN-21`.** Trois de ses mesures gouvernent ce lot — la distribution
> d'uniformité du fond local (L21.2), le drapeau `lecture_sure` (L21.3), la borne supérieure
> d'aire (L21.1). **Sans elles, ce plan n'est pas exécutable**, il est seulement écrivable.

---

## 1. La question d'architecture, à trancher avant toute ligne de code

Le principe directeur du projet, README §12, est **« l'IA ne dessine jamais »**. Il n'est pas
décoratif : trois mécanismes en dépendent.

- `clean.py` a un invariant pixel-exact — une seule écriture, `out_arr[paint] = style.background`,
  précédée de `paint = paint & region.mask`, filet conservé même quand il est redondant en
  théorie « parce que l'invariant ne doit pas dépendre d'un raisonnement ». Vérifié hors masque
  par `tests/test_manga_clean.py`.
- `typeset.calque_fit` **multiplie l'alpha par `style.interior`**, présenté comme « l'exact
  miroir du `paint &= region.mask` de `clean.py` ».
- Et le refus est écrit trois fois, dont une avec sa justification complète : « Les retirer
  demanderait de reconstruire le dessin qu'ils recouvrent, donc un modèle génératif (LaMa chez
  koharu) — ce que le principe directeur interdit. À la place, la traduction est POSÉE À CÔTÉ,
  comme le fait la fantrad à la main depuis toujours. Le japonais reste visible et intact ;
  **c'est un choix, pas un échec**. »

**Cette phrase est juste, et elle reste juste.** Ce plan ne l'abroge pas. Il propose de la rendre
**précise**, parce qu'en l'état elle interdit deux choses très différentes sous le même mot :

| Ce que le principe interdit vraiment | Ce qu'il interdit par effet de bord |
|---|---|
| qu'un modèle génératif décide silencieusement, dans le chemin par défaut, de réécrire des pixels de dessin qu'un utilisateur ne relira jamais | qu'un utilisateur qui le demande explicitement obtienne un calque d'effacement séparé, réversible, désactivé par défaut, et signalé |

**La reformulation proposée, à soumettre à l'auteur avant de coder :**

> **L'IA ne dessine jamais dans le chemin par défaut, et jamais de façon irréversible.**
> Un effacement de fond est un **calque distinct**, jamais aplati dans le rendu sans que
> l'utilisateur l'ait demandé, toujours listé dans `RAPPORT.md`, et toujours annulable en
> supprimant un fichier de cache.

⚠ **Trois raisons de penser que cette reformulation est acceptable, et une de penser le
contraire.**

Pour :
1. Elle conserve l'invariant de `clean.py` **intact** : l'effacement de hors-bulle est un
   nouveau chemin, il ne passe pas par `clean_bubbles` et ne touche pas à son test.
2. Elle conserve la propriété qui fait la valeur du projet : **rien ne quitte la machine**. Un
   modèle d'inpainting local ne change pas cela d'un octet.
3. Le projet a déjà exactement ce patron ailleurs : `mode: "rapport"` par défaut, `"glose"` en
   connaissance de cause. Un troisième cran opt-in est cohérent avec sa culture.

Contre :
1. Le principe est un **argument de communication** autant qu'une décision technique. « L'IA ne
   dessine jamais » se dit en cinq mots ; « l'IA ne dessine que dans un calque réversible que
   vous avez demandé » ne se dit pas en cinq mots. C'est un coût réel, et il n'est pas
   technique.

**Ce plan ne tranche pas à la place de l'auteur.** L'étape 0 est une décision, pas une mesure.

---

## 2. Étape 0 — Décider, puis mesurer ce que le déterministe peut faire

### 0.1 — La décision d'architecture

Écrire la reformulation retenue — ou le refus — dans `README.md` §12 et dans
`docs/ai-provenance.md`, **avant** d'écrire du code. Si la réponse est « non, aucun modèle
génératif, jamais », le lot se réduit à L22.1, L22.4 et L22.5 : c'est un lot plus petit, entièrement
déterministe, et parfaitement défendable.

### 0.2 — Combien de cas le déterministe suffit-il à traiter ?

Reprendre la distribution d'uniformité du fond local de `PLAN-21` L21.2 et la lire avec l'échelle
de `clean.py`, qui est déjà calibrée sur 797 bulles :

| Uniformité du fond local | Ce qu'un remplissage de couleur unique donnerait |
|---|---|
| ≥ 0,60 | correct. C'est le mode `"masque"` de `clean.py`, mesuré sur la médiane de 0,892 |
| 0,35 – 0,60 | passable sur le masque de texte dilaté seulement — le mode `"texte"`, 10 bulles sur 797 |
| < 0,35 | **destructeur.** C'est le gratte-ciel de la page 44 : uniformité 0,131, le mode « texte » repeignait toute la structure claire du bâtiment en noir, « le dessin est détruit » |

**Publiez la part de chaque tranche pour les zones hors bulle.** C'est le chiffre qui décide si un
modèle génératif est nécessaire ou si c'est une envie.

⚠ **Une hypothèse à vérifier et non à supposer** : une onomatopée est souvent posée sur une trame
mécanique, un aplat ou un flou de vitesse — des fonds **plus** uniformes que la moyenne d'une
planche. Si c'est vrai sur votre corpus, la tranche ≥ 0,60 peut être majoritaire et tout ce plan
se simplifie. Si c'est faux, dites-le.

---

## L22.1 — L'effacement déterministe, et il n'y a pas d'OpenCV

**Le cas nominal, à faire quoi qu'il advienne de la décision de l'étape 0.**

Pour une zone dont le fond local est uni : remplir le masque du glyphe, dilaté, par la couleur de
fond mesurée par `PLAN-21` L21.2. C'est exactement le mode `"texte"` de `clean.py`, transposé.
Aucun modèle, aucune dépendance.

Pour un fond faiblement structuré — un dégradé, une trame régulière — un remplissage par diffusion
suffit souvent, et il s'écrit en numpy pur : propager les valeurs de bord vers l'intérieur du
masque par itérations de moyenne, une vingtaine de passes. C'est l'algorithme de `cv2.inpaint` en
version naïve, sans la dépendance.

⚠ **Pas d'OpenCV.** `requirements-manga.txt` le refuse — « ~60 Mo pour trois opérations de
morphologie » — et `manga/geometry.py` fait déjà son érosion et sa dilatation en numpy pur, par
sommes cumulées, à coût indépendant de `k`. `cv2.inpaint` (Telea, Navier-Stokes) n'est donc pas à
portée d'import, et l'ajouter pour cette seule fonction serait une régression d'une décision
mesurée.

**Le garde-fou, et c'est le même que celui qui a sauvé la page 44 :** en dessous du seuil
d'uniformité, **on ne peint rien**. La zone garde son texte source — visible, donc corrigible à la
main — au lieu de coûter un morceau de planche. Le rapport le liste.

**Critère.** Des images avant/après sur les trois tranches d'uniformité, publiées. Un effacement
ne s'évalue pas par un tableau.

---

## L22.2 — Le modèle génératif, si l'étape 0 l'autorise

**Ce que le candidat identifié apporte, et ce qu'il coûte.**

`Qwen-Image` et sa variante d'édition sont sous **licence Apache-2.0** — vérifié le 2026-08-26 sur
le dépôt officiel. C'est un point décisif : le détecteur de bulles actuel est **GPL-3.0**, le
détecteur de texte est **GPL-3.0 amont avec des poids entraînés pour partie sur Manga109-s**
(usage académique), et `docs/chiffres-de-reference.md` les liste comme telles. Un modèle
Apache-2.0 est **plus propre que ce que le projet utilise déjà**.

**Le coût, en revanche, est le point dur.** Le modèle d'édition fait **20 milliards de
paramètres**. Les besoins matériels relevés le 2026-08-26 : **RTX 3060 12 Go minimum**, **BF16
demande 24 Go**, et une quantification GGUF Q4 tourne sur CPU. Le dépôt officiel mentionne par
ailleurs un déchargement couche par couche permettant l'inférence en 4 Go de VRAM.

⚠ **Confrontez cela à la contrainte réelle du projet, qui est écrite dans son dossier** : « la
contrainte réaliste est un modèle de 27 milliards de paramètres avec une fenêtre de 32k sur un GPU
grand public ». Le LLM de traduction occupe donc déjà le GPU. Faire cohabiter un modèle d'image de
20 milliards de paramètres avec lui sur la même carte n'est pas une question de réglage : c'est
une question de savoir lequel des deux est chargé à quel moment.

**Trois conséquences pratiques à traiter dans le plan, pas après.**

1. **La passe d'effacement est une passe séparée, jamais entrelacée avec la traduction.** Le
   pipeline a déjà cette forme : deux balayages du volume séparés par des passes de volume.
   L'effacement est un troisième balayage, qui charge son modèle, traite toutes les planches,
   et le décharge.
2. **Le coût s'ajoute à l'appel déjà le plus cher du pipeline.** Le détecteur de texte coûte
   **128 s par bande** et un pic de **+746 Mo** ; avec `onnxruntime-directml` la même passe tombe
   à 1,5-1,9 s sur planche paginée, un rapport de ~65×. Mesurez le temps et le pic mémoire de
   l'effacement dans les mêmes termes, et écrivez-les dans `perf.log` — le lot 14 a fait de la
   mémoire résidente un chiffre mesuré pour la première fois, ne perdez pas cet acquis.
3. **Ce ne peut pas être une dépendance de `requirements-manga.txt`.** Plusieurs gigaoctets de
   poids pour un mode opt-in que la majorité n'activera pas. Un `requirements-inpaint.txt`
   distinct, et le mode qui refuse proprement si l'import échoue — c'est déjà le patron du
   téléchargement automatique des poids : un fichier `.part` renommé en dernier, une erreur
   actionnable, jamais un plantage obscur.

⚠ **Et une alternative à mesurer avant de se décider.** LaMa est le modèle d'inpainting de
référence pour cet usage précis, et son **code est Apache-2.0**. ⚠ Mais **la licence des poids
`big-lama` n'est pas celle du code**, et je n'ai pas pu l'établir avec certitude — plusieurs
redistributions circulent avec des conditions différentes. **Vérifiez-la sur la source primaire
avant de l'envisager**, et si elle est non commerciale ou académique, écartez-la et écrivez-le :
le projet a déjà deux poids sous contrainte, un troisième rendrait la redistribution indéfendable.

LaMa est deux ordres de grandeur plus petit qu'un modèle de diffusion de 20 milliards de
paramètres, et il est *entraîné pour effacer*, pas pour générer. Si sa licence le permet, c'est
probablement le bon outil ; si elle ne le permet pas, Qwen est le repli propre.

---

## L22.3 — Le lettrage d'une onomatopée : quatre capacités qui manquent

**Le constat.** Le moteur de lettrage est rigoureux et il ne sait faire qu'une chose : un
**paragraphe droit, centré, à corps unique, découpé à un masque**. Vérifié par recherche sur
`manga/typeset.py` : **zéro** occurrence de `rotate`, `transform`, `courbe`, `warp`, `bezier` ;
les seules occurrences d'`angle` sont à l'intérieur du mot « rectangle ». (⚠ Ne cherchez pas
`path` : il y en a une quarantaine, toutes des chemins de police — `font_path`, `pathlib.Path`,
`load_font`.) `best_fit` cherche **un seul** corps par bulle, entre 11 et 60 px, avec un plancher
empruntable à 8 px.

Et la contrainte la plus dure est structurelle : `calque_fit` multiplie l'alpha par
`style.interior`, donc **tout ce qui sort du masque disparaît** — « écrit hors du calque, donc
simplement perdu ». Or redessiner une onomatopée exige de **sortir** du masque du texte source :
la traduction française d'un `ゴォォォ` n'a ni la même forme ni la même emprise.

`style_impose` permet d'imposer un rectangle arbitraire, mais « le rectangle enregistré devient à
la fois la zone d'habillage **et** le masque de découpe, et les deux ne peuvent plus diverger ».
On peut déplacer le cadre ; on ne peut pas s'en affranchir.

**À faire, par ordre de rapport et de risque.**

| # | Capacité | Coût | Risque |
|---|---|---|---|
| 1 | **Dissocier zone d'habillage et masque de découpe** | faible | ⚠ touche le miroir de `clean.py` — à faire par un paramètre explicite, jamais par défaut |
| 2 | **Rotation** du calque, angle donné par l'orientation dominante mesurée (`PLAN-21` L21.2) | moyen | faible : c'est une rotation de RGBA avant composition |
| 3 | **Contour épais**, non plus dérivé du mode de nettoyage mais réglé | faible | faible |
| 4 | **Corps variable par ligne** | élevé | élevé — et probablement inutile |

⚠ **Ne faites pas le 4.** Une onomatopée manuscrite a un corps variable par glyphe, une
inclinaison, une déformation. Reproduire cela, c'est écrire un moteur de typographie
expressive — hors périmètre, et le dépôt classe déjà « les onomatopées réellement relettrées »
comme de la R&D lourde. Un mot droit, incliné, à gros contour, bien placé, est **très au-dessus**
de ce que produit l'état actuel, et c'est ce que vise ce lot.

⚠ **Et deux garde-fous de `best_fit` sont calibrés pour des bulles** : `aire_min_bulle` à 900 px²
et le diagnostic `bulle_degeneree`. Une zone d'onomatopée passée telle quelle serait probablement
refusée. Le diagnostic géométrique est bon — il a montré que « le rapport a conseillé "raccourcir
la traduction" neuf fois sur ce tome et n'avait raison qu'une seule » — mais ses seuils doivent
être paramétrés par type de zone, pas contournés.

---

## L22.4 — Le calque PSD, qui est la vraie porte de sortie

**C'est l'étape la plus utile du lot, et la moins risquée.** À faire même si tout le reste est
abandonné.

**Le constat.** Le PSD produit aujourd'hui une pile propre : `Planche originale` (masquée),
`Planche nettoyée`, puis un calque de **type Photoshop** par bulle, nommé avec sa réplique
abrégée, réécrivable au clavier, validé par le moteur de Photoshop lui-même sur 4 planches et
34 calques. C'est du bon travail.

Mais : **aucun calque d'onomatopée n'existe.** Et en mode `"glose"`, les gloses sont perdues comme
calques — `fond_propre` est capturé **avant** le rendu, parce que `typeset_page` mute l'image
qu'on lui donne, et c'est ce `fond_propre` qui devient `Planche nettoyée`. Les gloses n'existent
donc que dans le composite aplati.

Résultat pour un letteur humain : le PSD lui donne un fond où les **bulles** sont vides, mais
l'onomatopée japonaise est **toujours là, en pixels, fusionnée au dessin**. Il doit tout faire à
la main, et la seule chose que le fichier lui offre gratuitement — la traduction — n'est pas dans
le fichier mais dans `RAPPORT.md`.

**À faire.**

1. Un calque `Effacement SFX` — les pixels reconstruits, **séparés**, au-dessus de
   `Planche nettoyée`. Le masquer le rend réversible d'un clic.
2. Un calque de type par zone hors bulle, `SFX 01` … `SFX NN`, nommé avec sa traduction abrégée,
   comme les calques de bulle.
3. **Les zones illisibles ont aussi leur calque**, vide, nommé avec le crop et une mention. Le
   letteur voit alors *où* il doit intervenir.
4. Capturer le fond **après** les gloses, ou capturer les deux : le choix se documente, mais
   perdre les gloses comme calques est un défaut, pas une décision.

⚠ Et les PSD de bande sont refusés au-delà de 30 000 px de côté, planche par planche, avec un
refus rapporté — acquis du lot 14, à ne pas casser en ajoutant des calques.

**Pourquoi cette étape est la plus utile.** Elle transforme un mode « on ne sait pas encore faire »
en un mode « voici tout ce qu'il faut pour le faire à la main en cinq minutes ». C'est exactement
la promesse que `config.yaml` fait déjà — « utilisables pour lettrer à la main dans Photoshop » —
et qu'il ne tient pas.

---

## L22.5 — L'aveu à ne pas oublier : une docstring est fausse

`text_detection.py` annonce que le texte trouvé est « traduit puis **glosé** à côté, par
`typeset.py` ». Or **le mot `glose` n'apparaît nulle part dans `typeset.py`** : il n'existe que
dans `text_detection.py`, `orchestrator_manga.py` et `config.yaml`. Le dessin de la glose se fait
dans `manga/rendu.py`.

C'est mineur, et c'est le genre d'écart que ce lot doit corriger en passant — le lot 14 a fait de
la chasse aux affirmations fausses du dépôt un livrable, et c'en est une.

---

## L22.6 — Le piège d'invalidation, à traiter avant de coder

`sfx` est aujourd'hui dans `checkpoints.CACHE_NON_BLOQUANT` : il ne dépend que de `detection` et
ne nourrit que `rendu`. C'est ce qui permet de corriger le rendu sans repayer la détection.

⚠ **Un mécanisme d'effacement change le NETTOYAGE.** Il faudrait donc faire entrer `sfx` dans le
graphe d'invalidation — et cela **périmerait tous les rendus existants** des 17 projets.

**Trois issues, à trancher explicitement dans le document du lot.**

1. **L'effacement est un étage nouveau**, après `nettoyage`, qui ne modifie pas `nettoyage` : il
   écrit son propre cache et sa propre image. `sfx` reste non bloquant, rien n'est périmé. **C'est
   la voie recommandée**, et c'est aussi celle qui rend le calque PSD séparé naturel.
2. `sfx` entre dans le graphe → **MAJEUR**, obligation de supprimer `build/` écrite en tête du
   CHANGELOG. À ne faire que si la voie 1 se révèle impraticable, et en le mesurant.
3. Le mode reste hors du pipeline : un outil séparé sous `tools/` qui produit des PSD enrichis à
   partir des caches. Le moins intégré, le moins risqué, et peut-être le bon premier pas.

---

## Critères d'acceptation

| # | Critère |
|---|---|
| 1 | La décision d'architecture est écrite dans `README.md` §12 et `docs/ai-provenance.md`, **avant** le code |
| 2 | La part de zones hors bulle dans chaque tranche d'uniformité est publiée. C'est le chiffre qui justifie ou non un modèle |
| 3 | L'effacement déterministe fonctionne sur la tranche ≥ 0,60, avec images avant/après publiées |
| 4 | Sous le seuil d'abandon, **rien n'est peint**, et c'est prouvé par un test |
| 5 | `tests/test_manga_clean.py` passe **inchangé** : l'invariant de `clean.py` est intact |
| 6 | Le mode est **opt-in**, le défaut est inchangé, et un utilisateur qui ne touche à rien obtient le rendu bit à bit identique — vérifié sur un volume |
| 7 | Le PSD porte un calque `Effacement SFX` masquable et un calque de type par zone. Ouverture vérifiée, ou refus propre écrit |
| 8 | Si un modèle est utilisé : sa licence est vérifiée **sur la source primaire** et écrite dans `docs/ai-provenance.md` ; son temps et son pic mémoire sont dans `perf.log` ; il vit dans un `requirements-*.txt` distinct ; son absence est refusée proprement |
| 9 | Le graphe d'invalidation est traité par la voie 1, 2 ou 3 de L22.6, explicitement, et aucun rendu existant n'est périmé sans que ce soit écrit en tête du CHANGELOG |
| 10 | Les zones `lecture_douteuse` de `PLAN-21` ne sont **jamais** effacées. C'est la garantie qui rend le lot défendable |
| 11 | Tous les critères repris un par un dans `docs/relettrage-<date>.md`, avec leur verdict, y compris les non tenus, et **avec des images** |

⚠ **Le critère 10 est le plus important de la liste.** Effacer une onomatopée sur une lecture
douteuse produit exactement le défaut que le projet a passé son temps à éviter : une erreur
dessinée à la place d'une erreur signalée.

---

## Ce que ce lot ne fait pas

- Aucun corps variable par glyphe, aucune déformation, aucun texte sur courbe. Une onomatopée
  manuscrite reproduite fidèlement reste hors périmètre, et le dépôt la classe déjà en R&D lourde.
- Aucun effacement dans le chemin par défaut. Jamais.
- Aucun effacement d'une zone dont la lecture n'est pas concordante.
- Aucun changement au traitement des **bulles** : `clean.py` et son invariant sont intacts.

---

## Sources vérifiées le 2026-08-26

- [QwenLM/Qwen-Image](https://github.com/QwenLM/Qwen-Image) — « Qwen-Image is licensed under
  Apache 2.0 » ; variantes `Qwen-Image-2512`, `Qwen-Image-Edit-2511`, `Qwen-Image-Layered` ;
  déchargement couche par couche annoncé pour une inférence en 4 Go de VRAM
- [Qwen/Qwen-Image-Edit](https://huggingface.co/Qwen/Qwen-Image-Edit) — **20 milliards de
  paramètres**, Apache-2.0
- [Besoins matériels de Qwen-Image-Edit-2511](https://lilting.ch/en/articles/qwen-image-edit-2511-local-specs)
  — RTX 3060 12 Go minimum, BF16 24 Go, GGUF Q4 sur CPU
- [advimman/lama](https://github.com/advimman/lama) — **code** Apache-2.0. ⚠ **La licence des
  poids `big-lama` n'a pas pu être établie** et doit être vérifiée sur la source primaire avant
  tout usage
- Les chiffres du dépôt (uniformité médiane 0,892 sur 797 bulles, seuil d'abandon 0,35 et le
  gratte-ciel à 0,131, 128 s et +746 Mo pour le détecteur de texte, rapport ~65× avec DirectML,
  285 444 px² de faux positif, 30 000 px de limite PSD) viennent de `config.yaml`, `manga/clean.py`
  et `manga/text_detection.py`, et sont à revérifier à l'étape 0 selon la règle de
  `docs/chiffres-de-reference.md`
