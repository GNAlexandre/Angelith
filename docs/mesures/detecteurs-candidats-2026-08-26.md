# Les détecteurs candidats — mesure du 2026-08-26 (lot 16, L9.0)

- **Date de mesure** : 2026-08-26
- **Commit** : `f826cd8`
- **Version du dépôt au moment de la mesure** : 2.7.1
- **`config.yaml`** : sha256 `d971be6abb9f`
- **Machine** : `CPUExecutionProvider` seul, AMD Ryzen 7 2700X. ⚠ Les durées absolues en
  dépendent lourdement.
- **Outil** : `tools/banc_candidats.py`, livré par ce lot. Rien n'a été écrit sous `build/` ;
  toutes les mesures sont des **rejeux** sur les planches de `sources/`.
- **Corpus** : les 10 volumes de `build/` (1 513 planches, dont 188 à zéro bulle) et le corpus
  annoté redistribuable `tests/corpus/synthetique`.

---

## Le résultat, en un paragraphe

**Aucun des deux poids Apache-2.0 ne remplace le détecteur en place, et le lot 16 ne s'arrête
pas ici.** Sur le webtoon — le chiffre qui devait décider — le taux de bulles sans texte ne
tombe pas : **13,2 %** pour le détecteur actuel, **13,8 %** pour `ogkalu/comic-speech-bubble-detector-yolov8m`,
**11,1 %** pour `ogkalu/comic-text-and-bubble-detector`. Le critère de sortie écrit dans le plan
(« le second avis ramène l'essentiel des planches à zéro bulle **et** fait tomber le taux de
faux positifs webtoon ») n'est pas rempli.

**Mais la mesure a trouvé autre chose, et c'est plus utile que ce qu'elle cherchait.** Sur les
188 planches à zéro bulle, le premier candidat en récupère **52 à 640** et **76 à 1 024** — un
chiffre spectaculaire, jusqu'à ce qu'on regarde ce qu'il a trouvé. Sur un échantillon de
**12 planches et 33 régions**, examinées une par une : **zéro ballon**. 22 régions sur 33 sont
du **texte de récit hors bulle** — récitatifs, dialogue sans ballon, cartouches, onomatopées —
6 sont du texte éditorial (titre, publicité, crédits), et 5 sont de fausses détections franches
(3 filigranes de scan, 2 morceaux de dessin).

Ce candidat n'est donc pas un meilleur détecteur de **bulles** : c'est un détecteur de
**texte**. Ses propres poids le disaient — ses classes embarquées s'appellent `text_bubble` et
`text_free` — et la fiche de son modèle ne le disait pas. C'est le lot 21 (lecture du texte hors
bulle) et le lot 13 (remplacer `comic-text-detector`, GPL-3.0 + Manga109-s) qu'il intéresse, pas
celui-ci.

---

## 1. Ce qui rend ce tableau citable

Avant tout chiffre : `tools/banc_candidats.py --actuel` **reproduit exactement** la mesure
publiée par le lot 14. Sur les 9 bandes de *webtoon A* Chap.11, il compte **53 bulles**,
c'est-à-dire le chiffre de [`webtoon-2026-08-26.md`](webtoon-2026-08-26.md) § 2, à l'unité près.

Ce n'était pas acquis. La première version de l'outil mesurait la sortie du réseau, et non ce
que le pipeline **écrit** : sur les trois premières bandes elle comptait **3, 7 et 13** bulles
là où le tableau final en compte **4, 9 et 13**. Le cache ne porte pas les détections brutes —
il porte le résultat de la scission des régions bi-lobées (`bubbles_split.scinder_regions`) puis
de `document.rendre_disjoints`. Un candidat mesuré sans ces deux étapes afficherait
mécaniquement moins de bulles que le détecteur en place, et l'écart mesuré serait celui du
post-traitement, pas des poids. D'où `banc_candidats.finaliser`, qui les applique à **tous** les
bras, candidats compris.

> ⚠ **Une réserve, et elle vaut d'être écrite.** Le cache de `build/` porte **59** bulles sur ces
> mêmes 9 bandes, contre 53 aujourd'hui. Ce n'est pas une divergence de mesure : c'est que le
> cache date de la v1.8.0 et que le dédoublonnage de coutures du lot 12 en a retiré 6 depuis. Le
> cache n'a pas été réécrit — `build/` est en lecture seule. Les colonnes
> « gagnées/cache » et « perdues/cache » se lisent donc **contre un cache périmé**, et c'est la
> comparaison bras à bras, mesurée dans le même run, qui fait foi.

---

## 2. Le chiffre qui devait décider : le webtoon

9 bandes de 1080×10 000, source anglaise, `input_size` 640 pour les trois bras, fenêtrage et
post-traitement identiques. **L'OCR du projet a été relancé sur chaque bulle trouvée**
(`rapidocr` via `ocr_routeur`, comme le pipeline) : une bulle dont l'OCR ne tire rien n'aura pas
de réplique, donc verra son dessin recollé par `rendu.restaurer_sans_texte`. C'est le substitut
mesurable des « zones restaurées », et le plus proche qu'un rejeu permette.

| détecteur | licence | bulles | sans texte OCR | **taux** | non nettoyables | IoU masque |
|---|---|---|---|---|---|---|
| `kitsumed/yolov8m_seg` *(actuel)* | GPL-3.0 | 53 | 7 | **13,2 %** | 2 | 0,99 |
| `ogkalu/comic-speech-bubble-detector-yolov8m` | Apache-2.0 | **65** | 9 | **13,8 %** | 1 | 0,89 |
| `ogkalu/comic-text-and-bubble-detector` | Apache-2.0 | 63 | 7 | **11,1 %** | 2 | 0,88 |

**Lecture.** Le premier candidat gagne **12 bulles** (+22,6 %) et son taux de fausses détections
**monte** de 0,6 point : il voit plus, pas mieux. Le second gagne **10 bulles** et fait baisser
le taux de **2,1 points** — c'est un vrai gain, le seul de ce tableau, et il est trois fois plus
petit que ce qu'il faudrait pour approcher la cible de 5 % que le lot 14 s'était fixée et n'a
pas atteinte.

⚠ **Une bulle réellement perdue.** Le premier candidat rend **0 bulle** sur la bande 9, là où le
détecteur en place en trouve 1 — c'est la seule planche du corpus qu'un candidat rend muette
alors que l'actuel ne l'était pas. Le tableau la compte dans sa colonne « 0 bulle » (1 planche).

⚠ **Le taux 13,2 % du détecteur actuel n'est pas le 15,1–17,0 % publié par le lot 14**, et les
deux sont justes. Le lot 14 lisait `ocr.json` + `traduction.json` du cache (donc l'OCR de la
v1.8.0, sur les bulles de la v1.8.0) ; ici l'OCR est **relancé** sur les 53 bulles d'aujourd'hui.
Deux dénominateurs, deux protocoles ; c'est le tableau ci-dessus, mesuré d'un bloc, qui compare
les trois détecteurs entre eux.

---

## 3. Les 188 planches à zéro bulle

Le second chiffre demandé par le plan. Les 188 planches que le cache rend muettes, rejouées par
les trois détecteurs, à deux résolutions.

| détecteur | `input_size` | bulles trouvées | planches récupérées | planches encore muettes | non nettoyables | sans texte OCR | sans texte (2ᵉ modèle) |
|---|---|---|---|---|---|---|---|
| `kitsumed` *(actuel)* | 640 | 0 | **0** | 188 | 0 | — | — |
| `kitsumed` *(actuel)* | 1024 | 26 | **19** | 169 | 0 | non mesuré | non mesuré |
| `ogkalu` YOLOv8m | 640 | 106 | **52** | 136 | 0 | **0** | **24 (22,6 %)** |
| `ogkalu` YOLOv8m | 1024 | 174 | **76** | 111 | 1 | non mesuré | non mesuré |
| `ogkalu` RT-DETR-v2 | 640 | 22 | **19** | 169 | 0 | **0** | **6 (27,3 %)** |
| `ogkalu` RT-DETR-v2 | 1024 | 3 | 3 | 185 | 0 | non mesuré | non mesuré |

Quatre choses à en tirer, et les deux dernières annulent les deux premières.

1. **La résolution seule vaut 19 planches** au détecteur en place — sans changer de poids, sans
   ajouter 100 Mo au projet. C'est le levier du lot 12, et le tableau le confirme.
2. **Le premier candidat en récupère 4 fois plus** à sa résolution d'entraînement.
3. **`clean.analyze_bubble` ne filtre rien ici** : sur les 106 régions à 640, **zéro** tombe
   sous `nettoyage.seuil_abandon` (0,35) ; l'uniformité minimale mesurée est **0,383**. Le plan
   du lot 16 posait que « un remplissage qui trouve une région uniforme a trouvé une bulle ».
   **C'est faux, et c'est mesuré** — voir § 4.
4. **Une région gagnée sur quatre ne porte aucun texte**, d'après un modèle étranger au chemin
   d'OCR : 24 sur 106, et 6 sur 22.

> ⚠ **`sans texte OCR` vaut ZÉRO sur ces neuf volumes japonais, et ce zéro ne veut rien dire.**
> `manga-ocr` est un modèle **génératif** de dialogue : sur 106 régions dont une bonne part est
> du dessin ou un filigrane, il n'a rendu **aucune** chaîne vide. C'est la mesure directe de ce
> que `tools/banc.py` annonce depuis toujours — « 0 bulle sans texte OCR » sur le manga paginé —
> et cela ne prouve pas qu'il n'y a pas de fausse détection : cela prouve que l'OCR ne les
> trahit pas par un silence. D'où l'option `--texte` du banc, qui interroge
> `comic-text-detector` sur un crop de chaque bulle et compte celles dont le texte couvre moins
> de 1 % du masque — le creux relevé par le lot 14 (§ 7) entre les muettes (0,00–0,41 %) et les
> lues (3,70–4,08 %). C'est **cette** colonne qui porte l'information ici, et c'est la seule
> raison pour laquelle le § 2 est mesuré sur le webtoon, seul volume à source latine, où
> `rapidocr` rend bel et bien une chaîne vide.

---

## 4. Ce que les 106 régions récupérées sont vraiment

C'est le point où la mesure automatique s'arrête et où il faut regarder les planches. Échantillon
de **12 planches sur les 52** récupérées à 640, couvrant **les neuf volumes concernés** — le
webtoon n'a aucune planche à zéro bulle — et les deux régimes (pages liminaires et pages de
contenu). **33 régions**, examinées une par une sur la planche annotée.

| planche | régions | ce que c'est |
|---|---|---|
| manga A Vol.1 p43 | 4 | 2 **récitatifs** blancs sur noir + 2 **filigranes** de scan |
| manga A Vol.1 p57 | 2 | 1 **cartouche** lieu/heure (北京／09:38) + 1 filigrane |
| manga A Vol.2 p145 | 2 | 2 **récitatifs** blancs sur noir |
| manga A Vol.3 p147 | 3 | page de fin : « To be continued », **crédits**, mention d'édition |
| manga A Vol.4 p139 | 2 | 2 morceaux de **skyline** — du dessin. Et le vrai texte de la planche (もう一人の妹よ) n'est **pas** détecté |
| manga C Vol.1 p5 | 2 | **titre de couverture** + **encart publicitaire** |
| manga C Vol.1 p96 | 6 | 6 fragments de **dialogue hors bulle**, découpés là où le dessin coupe |
| manga B Chap.5 p51 | 2 | 2 **onomatopées** (コッ…) |
| manga D Vol.1 p89 | 1 | 1 ligne sur 2 d'un **dialogue hors bulle** |
| manga D Vol.15 p86 | 6 | 6 **blocs de dialogue sans ballon** — le meilleur cas du corpus |
| manga D Vol.2 p85 | 1 | 1 **bandeau de titre de chapitre** |
| manga D Vol.2 p172 | 2 | 2 **blocs de dialogue sans ballon** |

**Le décompte, sur 33 régions :**

| catégorie | régions | part |
|---|---|---|
| **ballons de dialogue** — ce que ce lot cherchait | **0** | 0 % |
| texte de récit hors bulle (récitatif, dialogue sans ballon, cartouche, onomatopée) | 22 | 67 % |
| texte éditorial hors récit (titre, publicité, crédits, bandeau) | 6 | 18 % |
| fausses détections franches (3 filigranes, 2 morceaux de dessin) | 5 | 15 % |

Les 15 % de fausses détections de cet échantillon sont **cohérents avec la mesure automatique**
du § 3 : le détecteur de texte y trouve **22,6 %** de régions sans texte sur les 106. Les deux
comptent des choses légèrement différentes — un filigrane *porte* du texte, donc il compte comme
faux ici et comme lu là-bas — et ils encadrent le même ordre de grandeur : **entre une région
gagnée sur sept et une sur quatre ne vaut rien.**

**Zéro ballon sur 33.** Ce n'est pas une surprise rétrospective : les poids du candidat portent
les noms de classes `{0: "text_bubble", 1: "text_free"}`, ce que la fiche de son modèle
(« speech bubble detection ») ne dit pas et que le relevé du lot 12 avait recopié de la fiche.
Sur une planche **qui a déjà des bulles**, ses boîtes épousent effectivement les ballons — page
12 du Vol.1 de *manga A*, ses 12 boîtes coïncident à quelques pixels près avec
les 12 bulles du cache. Mais sur une planche que le
détecteur en place rend muette, ce qu'il trouve est du texte, parce qu'il n'y a pas de ballon à
trouver.

⚠ **Et les deux morceaux de skyline sont le résultat le plus important de cette section.** Ils
mesurent **0,807 et 0,818** d'uniformité — non seulement au-dessus du seuil d'abandon (0,35),
mais au-dessus du seuil de nettoyage **plein masque** (0,60). Le nettoyeur les repeindrait
entièrement. La règle centrale de `manga/detection_retry.py` — « une région que le nettoyeur
refuserait de nettoyer ne doit pas être détectée » — reste vraie ; ce qui est faux est sa
réciproque, et c'est elle que le plan du lot 16 utilisait pour dire qu'un masque dérivé se
juge tout seul. **Un ciel brumeux se remplit aussi uniformément qu'une bulle.**

---

## 5. Le corpus annoté : rappel, précision, F1

Trois planches, 22 bulles annotées, redistribuables (`tests/corpus/synthetique`, AGPL-3.0). C'est
le corpus de la CI, il est **synthétique**, et il ne décide de rien tout seul — mais il est le
seul du dépôt à porter une vérité terrain.

| détecteur | `input_size` | rappel | précision | F1 | bulles détectées / 22 |
|---|---|---|---|---|---|
| `kitsumed` *(actuel)* | 640 | 0,82 | 1,00 | 0,90 | 18 |
| `kitsumed` *(actuel)* | 1024 | 0,77 | 1,00 | 0,87 | 17 |
| `ogkalu` YOLOv8m | 640 | **0,86** | 1,00 | **0,93** | 19 |
| `ogkalu` YOLOv8m | 1024 | **0,86** | 1,00 | **0,93** | 19 |
| `ogkalu` RT-DETR-v2 | 640 | **0,86** | 1,00 | **0,93** | 19 |
| `ogkalu` RT-DETR-v2 | 1024 | 0,18 | 1,00 | 0,31 | 4 |

Deux faits, tous deux contre-intuitifs :

- **Relever `input_size` à 1024 fait BAISSER le rappel du détecteur en place** sur ce corpus
  (0,82 → 0,77). Ce n'est pas contradictoire avec le § 3, où 1024 récupère 19 planches muettes :
  la résolution aide là où les bulles sont petites et nuit là où elles sont grandes. Le corpus
  synthétique n'a que trois planches ; ce chiffre appelle une vérification sur du réel avant
  d'en tirer quoi que ce soit.
- **RT-DETR-v2 s'effondre à 1024** — 0,18 de rappel, 4 bulles sur 22. Son export accepte des axes
  dynamiques, mais ses requêtes ont été apprises à 640 et n'y survivent pas. **Conséquence
  directe** : ce candidat ne peut pas bénéficier du levier `input_size` du lot 12, ni de
  l'escalade à 1024. C'est une limite structurelle, pas un réglage.

Précision de 1,00 partout : **le masque dérivé par remplissage suffit à apparier** à IoU ≥ 0,50.

---

## 6. Une boîte remplie vaut-elle un masque ?

La question que le plan pose avant toute intégration. Mesurée sur les bulles que le candidat et
le détecteur en place voient au même endroit, par IoU des masques :

| | IoU moyen du masque dérivé contre le masque du réseau |
|---|---|
| `ogkalu` YOLOv8m | **0,89** |
| `ogkalu` RT-DETR-v2 | **0,88** |
| *(témoin)* `kitsumed` contre son propre masque en cache | 0,99 |

**0,88–0,89, c'est utilisable et ce n'est pas équivalent.** Au-dessus du seuil d'appariement du
banc (0,50), largement — mais 11 points de masque en moins, c'est un contour de bulle que
`clean.py` peindra un peu trop court ou un peu trop long, et un calque PSD qui ne suit pas le
trait. Pour un **second avis** sur une planche qui n'a rien, c'est suffisant ; pour remplacer le
détecteur principal, ça ne l'est pas — ce que `manga_models/README.md` disait déjà, sans le
chiffre.

Le remplissage lui-même est dans `tools/banc_candidats.masque_par_remplissage`, et il a un piège
qu'il vaut mieux écrire : **le germe est le quart central de la boîte, pas le pixel central.**
Sur une bulle dense en texte, le pixel du milieu tombe une fois sur deux dans une lettre, et le
remplissage ne trouve alors aucune composante — la bulle est perdue en silence. C'est arrivé sur
la planche de test du dépôt, dont une ligne de texte passe pile au centre.

---

## 7. Quatre affirmations corrigées par la mesure — deux du dépôt, deux du plan

| affirmation | mesure |
|---|---|
| `manga_models/README.md` : `ogkalu/comic-speech-bubble-detector-yolov8m` → « bulles, boîtes » | Ses poids déclarent `{0: "text_bubble", 1: "text_free"}`, et sur les planches muettes il ne trouve **aucun ballon** sur 33 régions |
| le même : « Exporter les deux candidats en ONNX » | Le second **est déjà** en ONNX (`detector.onnx`) ; le premier n'existe **qu'en `.pt`** et demande `ultralytics` — donc `opencv-python`, que `requirements-manga.txt` refuse |
| plan du lot 16 : « un remplissage qui trouve une région uniforme a trouvé une bulle » | **Faux.** Deux morceaux de skyline à 0,807 et 0,818 d'uniformité, au-dessus même du seuil de nettoyage plein masque |
| plan du lot 16 : les candidats sont mesurables « au même `input_size` » | Vrai pour l'un, **faux pour l'autre** : RT-DETR-v2 passe de 0,86 à 0,18 de rappel entre 640 et 1 024 |

---

## 8. Les critères du plan, un par un

| critère (L9.0 / acceptation du lot) | verdict |
|---|---|
| « L9.0 est fait et ses chiffres sont publiés, sur le manga *et* sur le webtoon » | **tenu** — ce document, plus `tools/banc_candidats.py` qui le reproduit |
| « Le taux de zones restaurées sur les 9 bandes » (référence 24 %, puis 15–17 %) | **mesuré** : 13,2 % (actuel) · 13,8 % (YOLOv8m) · 11,1 % (RT-DETR). **Aucun candidat ne le fait tomber de façon décisive** |
| « Le nombre de planches à zéro bulle récupérées » (référence 188 / 1 513) | **mesuré** : 52 à 640 et 76 à 1 024 pour YOLOv8m, 19 pour RT-DETR, 19 pour le détecteur actuel à 1 024. Mais **0 ballon sur 33 régions examinées**, et **22,6 %** des régions gagnées ne portent aucun texte |
| « Si le second avis ramène l'essentiel des planches à zéro bulle **et** fait tomber le taux webtoon, ce lot s'arrête ici » | **NON rempli.** La conjonction échoue sur son second terme, et son premier terme ne mesure pas ce qu'on croyait |
| « Les quatre seuils de L9.3 sont écrits dans le dépôt **avant** le premier entraînement » | **tenu** — [`seuils-affinage-detecteur.md`](seuils-affinage-detecteur.md), écrit ce jour, aucun entraînement n'ayant eu lieu |
| « Tout corpus utilisé a sa licence écrite dans un fichier du dépôt » | **tenu** pour la mesure : corpus synthétique AGPL-3.0 (`tests/corpus/synthetique`), corpus réel non redistribuable et jamais commité. Le corpus d'**entraînement** n'existe pas encore |
| « Le résultat, positif ou négatif, est dans `docs/` avec ses chiffres » | **tenu** |

---

## 9. La décision

1. **Ne pas remplacer le détecteur de bulles.** Les deux candidats sont Apache-2.0 et le poids
   en place est GPL-3.0 ; c'était l'argument le plus fort en leur faveur, et il ne suffit pas.
   Aucun ne rend de masques, aucun ne fait tomber le taux de fausses détections webtoon de façon
   décisive, et le premier ne détecte pas des ballons.
2. **Ne pas les brancher en second avis derrière l'escalade** — pas en l'état. Sur les
   188 planches muettes, ce qu'ils proposent est du texte hors bulle, et le faire entrer par la
   porte `kind="bulle"` le ferait nettoyer et relettrer **comme du dialogue**, avec sa place
   numérotée dans le prompt du traducteur. C'est un défaut plus grave que la planche muette
   qu'il prétend réparer.
3. **Reporter `ogkalu/comic-speech-bubble-detector-yolov8m` au lot 21** (lire le texte hors
   bulle) et à la question ouverte du lot 13 : `comic-text-detector` est **GPL-3.0 + Manga109-s**,
   et un candidat Apache-2.0 qui trouve 22 régions de texte de récit là où le pipeline ne voit
   rien mérite d'y être mesuré. `ogkalu/comic-text-segmenter-yolov8m` (Apache-2.0, ~3 000 images,
   **masques** de texte) doit être mesuré en même temps, et c'est probablement le meilleur des
   deux pour cet usage-là.
4. **Le lot 16 continue** — L9.1 à L9.4 — puisque son étape zéro n'a pas conclu à l'abandon. Le
   sous-comptage du webtoon (5,9 bulles par bande là où 25 à 35 sont attendues) reste entier, et
   aucun poids public ne le règle. Les seuils qui l'encadrent sont écrits.
5. **Ne pas ajouter de poids au dépôt.** Aucun `.onnx` candidat n'est commité, aucune URL n'entre
   dans `manga/models.py`, aucune clé de `config.yaml` ne change. Ce lot ne modifie **rien** au
   comportement livré.

---

## 10. Ce que cette mesure ne dit pas

- **Elle ne dit rien du webtoon en général.** Un seul chapitre, 9 bandes, 53 bulles, et c'est
  aussi le seul volume à source latine du dépôt. Les deux effets restent confondus, comme le
  lot 14 l'avait écrit.
- **L'échantillon du § 4 est de 12 planches sur 52, et il a été labellisé à la main.** Il oriente
  fortement — zéro ballon sur 33 régions ne s'inverse pas avec 40 planches de plus — mais il
  n'est pas un décompte exhaustif.
- **La colonne « sans texte OCR » ne vaut rien sur du japonais**, et c'est mesuré ici, pas
  supposé : **0 chaîne vide sur 106 régions**, dont une part est du dessin. C'est pourquoi le
  § 2 est mesuré sur le seul volume à source latine, où `rapidocr` rend bien une chaîne vide, et
  pourquoi `--texte` existe.
- **Le seuil de 1 % de couverture de texte vient d'un échantillon de 5.** Le lot 14 (§ 7) a
  relevé 0,00 / 0,00 / 0,41 % sur des bulles muettes et 3,70 / 4,08 % sur des bulles lues. Le
  creux est large et le seuil tombe dedans, mais cinq observations ne font pas une calibration :
  les 22,6 % du § 3 sont un ordre de grandeur, pas une décimale.
- **Aucun rendu n'a été produit.** « Zones restaurées » est une mesure d'après-rendu ; ce qui est
  publié ici en est le substitut le plus proche qu'un rejeu permette, pas la chose elle-même.
- **Les poids candidats ne sont pas dans le dépôt et ne peuvent pas y être** (100 à 170 Mo). La
  façon de les récupérer et de les exporter est dans
  [`manga_models/README.md`](../plans/README.md) ; les empreintes y sont relevées, si bien
  que la mesure est reproductible sans que le dépôt grossisse.
