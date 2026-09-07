# PLAN 21 — Lire l'onomatopée avant de prétendre l'écrire

> **Lire `00-CONTEXTE-AGENT.md` d'abord.**
>
> **Nature attendue** — MINEUR. Nouveau mode de lecture, nouvelles bornes, nouvelles mesures ;
> aucun cache invalidé, aucun pixel de dessin touché. **Ce lot ne dessine rien** — c'est
> `PLAN-22` qui négocie ce droit, et il ne peut pas être livré avant celui-ci.
>
> **Charge estimée** — 10 jours.
>
> **⚠ C'est le prérequis absolu de `PLAN-22`.** Ne les inversez pas. Effacer une onomatopée et
> la redessiner à partir d'une lecture fausse, c'est remplacer un défaut signalé par un défaut
> dessiné. Le dépôt le dit déjà, trois fois : « une mauvaise réplique dessinée est PIRE qu'une
> absence signalée ».

---

## Le constat : la détection marche, la lecture non

C'est écrit noir sur blanc dans `config.yaml`, et c'est le passage central de tout ce dossier :

> « La **DÉTECTION** est fiable — elle trouve bien la colonne de katakana de la page 63, que rien
> ne voyait avant. La **LECTURE** ne l'est pas : `manga-ocr` est un modèle de **DIALOGUE**, qui
> rend toujours une phrase japonaise plausible. »
>
> « Passe à "glose" en connaissance de cause : **le placement, lui, est sûr** […] C'est le
> **CONTENU** qui n'est pas fiable. »

Les trois cas mesurés, tous sur le Vol.2 du manga de référence :

| Planche | Source réelle | Ce que `manga-ocr` a lu |
|---|---|---|
| page 63 | `ゴォォォ`, colonne de **1 470 px** de haut | « こっちは » puis « きゃあああっ » |
| page 135 | une onomatopée | « それは… », « しかし、 », « いや… » |
| page 25 | **une zone de dessin**, pas du texte | « 民主の人とセックスを » |

Et : « les **trois découpes testées** échouent également ».

⚠ **La seconde famille d'hallucinations est du latin produit sur une source JAPONAISE**, et
non l'inverse : `ＥｌｅＨＴ`, `［ｉｓｕｃｅ］`, `ＯＦＦＦＩＮＥ`, `ＲａｙＬｉｎｇｅｒ．` sont ce que
`manga-ocr` rend quand il hallucine **sur du dessin**. C'est précisément pourquoi `trier_zone`
inverse son heuristique avec la langue source : sur source japonaise, des lettres latines
signalent une hallucination ; sur source latine, ce sont elles qui portent le contenu et le CJK
qui est l'intrus. **Ne recopiez pas cette liste comme un défaut du chemin latin** — l'inverser
ferait jeter le vrai contenu d'un webtoon anglais.

C'est pourquoi le mode livré est `"rapport"` : détecter, lire, traduire, et **n'écrire que dans
`RAPPORT.md`**. Ce n'est pas de la prudence excessive, c'est la conclusion d'une mesure.

### Et trois autres manques, moins visibles, qui comptent autant

1. **Il n'existe aucune borne SUPÉRIEURE d'aire** dans `hors_des_bulles`. Mesuré sur un liminaire
   illustré : la plus grosse zone fait **285 444 px², soit 2,6 % de la bande** — « du dessin pris
   pour du texte, pas une onomatopée ». Aujourd'hui c'est une ligne parasite au rapport. Avec
   effacement, c'est 2,6 % de planche détruite.
2. **`clean.analyze_regions` fabrique un style vide pour toute onomatopée.** Pour `kind !=
   "bulle"`, il rend `interior = zeros`, `background = (255,255,255)`, `inverted = False`,
   `uniformity = 0.0`, `ok = False` — délibérément, afin que la liste reste **alignée par
   position** avec `regions`, `ocr.json` et `traduction.json`. Donc **rien n'est mesuré** sur une
   onomatopée : ni la couleur d'encre réelle, ni la polarité, ni le fond local.

   ⚠ Et `clean.py` prévient : « Ces informations ne peuvent pas être redécouvertes après le
   nettoyage. » Un `ゴォォォ` est typiquement blanc à contour noir sur dessin sombre, ou l'inverse :
   la polarité `inverted=False` codée en dur est **fausse une fois sur deux**.
3. **Rien ne valide qu'une réponse du LLM est bien une onomatopée.** `_translate_sfx` réutilise
   `try_with_temp_retry`, `bubbles_cap` et `repliques_par_bulle` — des garde-fous de **dialogue**.
   Une hallucination bien formée les passe tous.

---

## Étape 0 — Mesurer l'ampleur, et sur quoi

**Aucune ligne de code de ce lot avant publication et relecture.** Trois mesures, dont la
troisième est la plus importante.

### 0.1 — L'état des zones hors bulle sur tout `build/`

```powershell
python tools/banc.py --tous --markdown > docs/sfx-avant-<date>.md
```

À compléter, par volume : nombre de zones hors bulle, verdicts du triage lexical
(`TRI_MOBILIER` / `TRI_BRUIT` / `TRI_PONCTUATION` / `TRI_TEXTE`), et **la distribution des
aires** — c'est elle qui donne la borne haute de L21.1.

Les chiffres de référence à retrouver ou corriger : 448 zones sur le Vol.1 du manga A, 217 sur le
manga B ; 283 filigranes annoncés d'un côté, **92 zones de mobilier attrapées** de l'autre, sur
le même dénominateur de 448. **Le dépôt ne réconcilie pas ces deux nombres.** C'est exactement le
genre d'écart que `docs/chiffres-de-reference.md` existe pour trancher : faites-le.

### 0.2 — Un échantillon de vérité terrain, à la main

⚠ **Sans lui, ce lot ne peut rien conclure.** Il n'existe aujourd'hui aucune référence pour la
lecture d'une onomatopée : les trois erreurs citées ont été trouvées à l'œil, une par une.

**60 zones**, tirées au sort sur les volumes de `build/`, **graine écrite dans le dépôt**, avec
pour chacune : la transcription réelle du glyphe, sa nature (onomatopée / narration libre /
mobilier / dessin), et sa polarité (encre claire sur fond sombre, ou l'inverse). Une demi-journée
de travail à l'œil, et c'est le socle de tout ce qui suit.

⚠ **Ne l'ajoutez pas au corpus annoté du dépôt sans vérifier la licence des planches.** Le corpus
commercial est purgé, une fois pour toutes. Si les 60 zones viennent d'œuvres non
redistribuables, gardez **les mesures** dans le dépôt et les images dehors, et écrivez que le
banc n'est pas reproductible par un tiers sur ce point. C'est honnête et c'est utilisable ; le
contraire ne l'est pas.

### 0.3 — Le taux d'erreur de `manga-ocr` sur ces 60 zones

C'est le chiffre qui manque au dossier. Trois cas à compter séparément :

- lecture **exacte** ;
- lecture **plausible mais fausse** — le cas dangereux, celui de la page 63 ;
- lecture **manifestement absurde** — au moins elle se voit.

Publiez-le. Si le taux d'exactitude dépasse 80 %, une bonne part de ce plan devient discutable et
il faut le dire. S'il est sous 30 %, L21.3 devient le cœur du lot.

---

## L21.1 — Une borne supérieure d'aire, et un garde-fou de forme

**À faire.**

1. **`manga.onomatopees.aire_max_frac`**, en fraction de l'aire de la planche. Le dépôt normalise
   déjà ainsi ailleurs (`adaptive_radius` par le petit côté, `GROUPEMENT_FRAC` par
   `min(forme)`) ; les deux seuils qui restent en pixels absolus — `aire_min` à 1 200 px²,
   `scission.aire_min` à 10 000 px² — sont précisément ceux qui cassent sur un scan basse
   résolution.
2. **Le seuil vient de la mesure de l'étape 0**, pas d'un chiffre rond. La zone de 285 444 px² à
   2,6 % de la bande donne l'ordre de grandeur ; la distribution donne la valeur.
3. ⚠ **Livrez-la désarmée** (`0.0` = pas de borne) si la mesure ne sépare pas nettement le
   dessin du texte. Le lot 14 a livré trois réglages désarmés pour cette raison, mesure en main.
   Une borne mal placée jette de vraies onomatopées, et une onomatopée jetée ne se voit nulle
   part.
4. **Compter les rejets par motif** dans `RAPPORT.md`. Un filtre muet est la façon dont on perd
   les suivantes.

**Un garde-fou de forme, en plus de l'aire.** Une onomatopée est un **trait** : elle a une
grande étendue et une faible densité de remplissage dans sa boîte. Une zone de dessin prise pour
du texte a l'inverse. `geometry.remplissage` est déjà là, et sa calibration existe — sur les
**797 bulles** du tome de référence, « un ballon, même dentelé, remplit sa boîte (médiane
**0,89**) », et les vrais doubles bi-lobés tombent entre **0,72 et 0,91**.

⚠ Ces seuils sont calibrés sur des **bulles**. Rien ne dit qu'ils transposent à une zone hors
bulle, et c'est précisément ce qu'il faut mesurer : la distribution de remplissage sur les 60
zones de l'étape 0. Si les faux positifs s'en séparent, c'est un critère plus fin que l'aire
seule. Sinon, dites-le et gardez l'aire.

---

## L21.2 — Mesurer le style d'une zone hors bulle

**Le constat.** `analyze_regions` rend un style vide pour `kind != "bulle"`, et l'alignement par
position est la bonne raison de ne pas simplement changer ça.

**À faire — sans casser l'alignement.** Une fonction séparée, `analyser_zone_hors_bulle`, qui
rend un objet distinct et laisse `analyze_regions` intact. Elle mesure ce qu'un relettrage
exigera et qu'on ne pourra plus mesurer après :

| Mesure | Pourquoi |
|---|---|
| **polarité réelle** de l'encre | codée en dur à `False` aujourd'hui, fausse une fois sur deux |
| couleur de l'encre | pour un contour qui ne soit pas blanc par accident |
| couleur dominante du fond **autour** de la zone | le seul indice de ce que l'effacement devra reconstruire |
| **uniformité du fond local** | ⚠ **la mesure la plus importante du lot** — voir ci-dessous |
| étendue, remplissage, orientation dominante | pour L21.1 et pour `PLAN-22` |

La méthode existe déjà et est calibrée : histogramme de luminance Rec. 601 à 32 classes, classe
modale, affinage à ±16, **médiane RGB**. Le choix du mode plutôt que de la médiane ou d'un
percentile est documenté par une mesure — sur une bulle inversée, un p90 rend « la couleur **du
texte** ». Réutilisez-la ; ne réinventez pas une mesure de couleur.

### Pourquoi l'uniformité du fond local décide de `PLAN-22`

`clean.py` a une échelle à trois modes gouvernée par l'uniformité : ≥ 0,60 → remplir tout
l'intérieur ; 0,35 à 0,60 → remplir le masque de texte dilaté ; **< 0,35 → ne rien peindre**. Et
ce dernier seuil vient d'un contrôle visuel, pas d'un plan : sur la page 44, un **gratte-ciel aux
fenêtres sombres** avait été pris pour une bulle (uniformité 0,131) et le mode « texte »
repeignait toute la structure claire du bâtiment en noir — « le dessin est détruit ». Le 0,35
tombe dans un creux net : les deux cas pathologiques à 0,131 et 0,226, la suivante à 0,457.

**Transposé au hors-bulle, cela donne la question de `PLAN-22` sous forme mesurable :** quelle
part des onomatopées est posée sur un fond suffisamment uni pour qu'un remplissage de couleur
suffise, sans aucun modèle ?

Publiez cette distribution. Elle décide de tout :

- **beaucoup au-dessus de 0,60** → un remplissage déterministe suffit pour la majorité, et
  `PLAN-22` n'a pas besoin de modèle génératif pour son cas nominal ;
- **beaucoup sous 0,35** → l'effacement demande une vraie reconstruction, et `PLAN-22` doit
  affronter la question du principe directeur ;
- **une masse au milieu** → deux chemins, et un seuil à calibrer.

---

## L21.3 — Lire pour de vrai : trois voies, à mesurer avant de choisir

**Le vrai problème.** `manga-ocr` est un modèle de dialogue. Il ne peut pas lire une onomatopée
stylisée, et les trois découpes essayées ne changent rien. Le dépôt nomme lui-même la sortie :
« Le jour où un vrai recogniseur d'onomatopées sera branché (koharu en embarque un, avec son
propre jeu de caractères), "glose" deviendra le défaut naturel. »

**Trois voies, et il faut les mesurer sur les 60 zones de l'étape 0 avant de trancher.**

### Voie A — le modèle vision, sur un crop

C'est la voie la moins coûteuse en dépendances, parce que **tout est déjà là** : le client LLM est
OpenAI-compatible, le modèle de référence est vision-capable, et `MangaAgent.run(..., images=…)`
existe. Il manque uniquement l'envoi d'un **crop**, jamais fait dans le dépôt — les deux seuls
sites d'appel avec image joignent une planche pleine page.

Un modèle vision qui voit `ゴォォォ` écrit en 1 470 px de haut peut le lire, là où aucun OCR de
dialogue ne peut. Et le crop rectangulaire brut est le bon cadrage : `ocr.region_rectangulaire`
l'a déjà établi, mesure à l'appui — sur une zone hors bulle, l'encre isolée donne
`人間の場所．．．` (inventé) contre `ああ．．．陽弥．．．` (correct) pour le crop brut, parce que le
modèle se sert des demi-teintes.

⚠ **À mesurer, pas à supposer.** Un modèle vision généraliste peut halluciner sur une onomatopée
aussi bien qu'un OCR de dialogue — c'est la même famille de défaut. Le dépôt a d'ailleurs déjà
noté qu'au niveau du crop, le détecteur de texte « se comporte bien mieux » qu'à la planche : la
granularité aide, elle ne garantit rien.

### Voie B — un recogniseur d'onomatopées dédié

Celui de koharu, mentionné dans `config.yaml`, ou un autre. ⚠ **La licence est la première
question, pas la dernière** : le détecteur de texte actuel est GPL-3.0 amont avec des poids
entraînés pour partie sur **Manga109-s** (usage académique), et le dépôt l'avertit à trois
endroits. Un second poids sous la même contrainte alourdit le même problème.

Vérifiez la licence **avant** de mesurer quoi que ce soit. Si elle est incompatible avec une
redistribution AGPL, la voie est fermée et il faut l'écrire — c'est un résultat.

### Voie C — refuser de lire, et le dire mieux

La voie que personne n'aime et qui est peut-être la bonne pour une partie du corpus.

Une zone dont **aucune** voie ne donne une lecture concordante est marquée « illisible », et le
rapport la liste **avec son crop exporté** dans un dossier — pour qu'un humain puisse la
transcrire en dix secondes au lieu de rouvrir la planche et de la chercher. `RAPPORT.md` liste
déjà les onomatopées ; il ne fournit pas l'image.

C'est peu, et c'est immédiatement utile : cela transforme « il y a 260 zones de texte à traduire
quelque part dans ce tome » en une planche-contact que quelqu'un peut traiter.

### Le critère de décision entre les trois

**La concordance, pas la confiance.** Aucun de ces modèles ne rend un score de confiance
exploitable — `manga-ocr` rend toujours une phrase plausible, c'est tout le problème. En revanche,
deux voies indépendantes qui **s'accordent** sur une lecture sont un signal fort, et deux voies
qui divergent sont un signal fort dans l'autre sens.

Implémentez la concordance comme critère de première classe : une zone lue de la même façon par
deux voies est `lecture_sure` ; sinon elle est `lecture_douteuse` et part en voie C. C'est ce
drapeau, et lui seul, qui autorisera `PLAN-22` à dessiner.

---

## L21.4 — Valider qu'une traduction d'onomatopée est une onomatopée

`_translate_sfx` réutilise des garde-fous de dialogue. Rien ne dit qu'une réponse est bien une
onomatopée.

**À faire.** Un prédicat, dans l'esprit de `quality_manga.MOTIFS` et rangé dans le même registre
ordonné, qui refuse une réponse qui n'a pas la forme attendue : une phrase avec un verbe conjugué
et de la ponctuation de dialogue à la place de « VROOM », c'est le modèle qui a brodé. Le prompt
`manga_onomatopees` demande déjà une onomatopée ; il n'y a aucune vérification.

Le seuil se calibre sur les traductions déjà produites — elles sont dans `build/`, dans
`sfx_traduction.json`, pour 17 projets. Mesurez la distribution de longueur et de composition
avant de fixer quoi que ce soit.

⚠ Et la ponctuation pure ne doit **pas** passer par ce prédicat : `！！` et `．．．` sont rendus
déterministement par `typeset.latiniser`, sans LLM, et c'est un mécanisme mesuré — 81 zones sur
le manga A, 47 sur le manga B, rendues ainsi. Ne le cassez pas.

---

## L21.5 — Un mode `"glose"` qu'on puisse enfin évaluer

Le mode existe : dessiner la traduction **à côté** du japonais, qui reste visible. Il n'est pas
le défaut parce que le contenu n'est pas fiable — et L21.3 est précisément ce qui peut changer
cela.

**À faire.**

1. Mesurer le mode `"glose"` sur les zones marquées `lecture_sure` de L21.3, sur un volume, et
   **publier les images**. Un mode de rendu ne s'évalue pas par un tableau.
2. Ne le rendre défaut que si le taux de `lecture_sure` le justifie, et publier le taux dans les
   deux cas. Si la réponse est non, `"rapport"` reste le défaut et le lot a produit le chiffre
   qui le justifie — c'est un résultat, pas un échec.
3. ⚠ **Vérifier le contour.** `calque_fit` prend `stroke_fill = (*style.background, 255)`, et
   `analyze_regions` force `background = (255,255,255)` pour une onomatopée : **le contour d'une
   glose est donc blanc par construction**, quel que soit le dessin en dessous. Or
   `config.yaml` pose `glose_contour: true` avec le bon argument — « sur du dessin, c'est le
   contour qui fait la lisibilité ». Branchez-le sur la couleur mesurée par L21.2.

---

## Critères d'acceptation

| # | Critère |
|---|---|
| 1 | L'échantillon de 60 zones existe, sa graine est dans le dépôt, et sa licence est tranchée par écrit |
| 2 | Le taux d'erreur de `manga-ocr` sur ces 60 zones est publié, avec les trois catégories distinguées |
| 3 | **La distribution d'uniformité du fond local est publiée.** C'est la mesure qui décide de `PLAN-22` |
| 4 | L'écart 283 filigranes / 92 zones de mobilier sur le même dénominateur de 448 est **expliqué ou corrigé**, pas absorbé |
| 5 | La borne supérieure d'aire existe, avec le chiffre qui la justifie, ou est livrée désarmée avec le chiffre qui explique pourquoi |
| 6 | Le drapeau `lecture_sure` / `lecture_douteuse` existe et son taux est publié par volume |
| 7 | Les trois voies de L21.3 sont mesurées sur les 60 zones, licences vérifiées, et le choix est argumenté par des chiffres |
| 8 | Les crops des zones illisibles sont exportés et listés dans `RAPPORT.md` |
| 9 | Le contour de glose prend la couleur mesurée, plus le blanc par défaut |
| 10 | **Aucun pixel de dessin n'a été repeint par ce lot.** Vérifié par le test pixel-à-pixel de `tests/test_manga_clean.py`, qui doit passer inchangé |
| 11 | Les critères ci-dessus sont repris un par un dans `docs/sfx-<date>.md`, avec leur verdict, y compris les non tenus |

---

## Ce que ce lot ne fait pas

- **Il n'efface rien et ne reconstruit rien.** `clean.py` continue de passer sur
  `kind != "bulle"`, son invariant est intact, et le principe directeur n'est pas touché.
- Il ne rend pas `"glose"` défaut d'office — seulement si la mesure le porte.
- Il ne touche ni à la rotation, ni au corps variable, ni au calque PSD : `PLAN-22`.
- Il ne cherche pas un meilleur détecteur de **bulles** : c'est le lot 16.

---

## Sources vérifiées le 2026-08-26

- Les chiffres cités sans lien viennent du dépôt : `config.yaml`, `manga/text_detection.py`,
  `manga/clean.py`, `manga/orchestrator_manga.py`, `manga/typeset.py`. Chacun est à revérifier à
  l'étape 0 selon la règle de `docs/chiffres-de-reference.md` — plusieurs datent des rendus de la
  v0.40.0 et le dépôt le signale.
