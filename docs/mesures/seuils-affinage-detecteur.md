# Les quatre seuils de l'affinage du détecteur — écrits avant le premier entraînement

> **Ce fichier est un engagement, pas un rapport.** Il fixe **à l'avance** ce qui autoriserait
> à continuer un affinage du détecteur de bulles, et ce qui obligerait à l'arrêter. Il est
> écrit le **2026-08-26**, avant qu'une seule époque ait tourné, et c'est tout son intérêt :
> des seuils posés après coup sont des seuils qu'on ajuste jusqu'à ce qu'ils passent.
>
> Aucun entraînement n'a eu lieu à cette date. Aucun corpus d'entraînement n'a été constitué.

## Pourquoi ce fichier existe

Un affinage est un puits : il y a toujours une époque de plus à essayer, un taux
d'apprentissage à ajuster, une augmentation à ajouter. Sans nombre écrit d'avance, on ne sait
jamais si l'on progresse ou si l'on s'acharne — et on ne sait surtout jamais **quand publier
un résultat négatif**, qui est pourtant un livrable.

Le dépôt a déjà cette discipline ailleurs, et elle a déjà servi :

- `manga/bubbles_split.py` mène la sonde d'encre comme une évaluation à critère d'abandon
  écrit à l'avance, et la livre **désarmée** ;
- `manga/ocr_latin.py` a **rejeté sur mesure** le repli `use_det=False` ;
- le lot 14 a livré `fenetre_encre_min` et `aire_min_frac` à `0.0` parce que la mesure ne
  soutenait pas de les armer, et l'a écrit.

## La ligne de base, avec ses dénominateurs

Tout ce qui suit se mesure sur le **banc du lot 10** (`docs/procedures/banc-de-mesure.md`) et se compare
à ces chiffres-là, pas à d'autres.

| ligne de base | valeur | source |
|---|---|---|
| bulles sur les 9 bandes du webtoon de référence | **53**, soit 5,9 par bande | `docs/mesures/webtoon-2026-08-26.md` § 2 (rejeu 2.6.0) |
| taux de fausses détections sur ces 9 bandes | **15,1 – 17,0 %** | `docs/mesures/webtoon-2026-08-26.md` § 1 |
| zones restaurées sur les 9 volumes de manga paginé | **0** sur 7 803 bulles | `docs/mesures/banc-2026-08-25.md` |
| bulles sans texte OCR sur le manga paginé | **0** | idem |
| planches à zéro bulle, tous formats | **188** sur 1 513 (cache), dont **183 encrées** | `python tools/banc.py --tous` |
| détecteur de départ | `kitsumed/yolov8m_seg-speech-bubble`, **GPL-3.0** | `manga_models/README.md` |

⚠ **Le détecteur de départ n'est pas acquis.** Si l'étape L9.0 retient un poids **Apache-2.0**
comme base, la ligne de base change et ce fichier doit être **modifié avant** le premier
entraînement, pas après. Cf. `docs/mesures/detecteurs-candidats-2026-08-26.md`.

---

## Seuil 1 — le gain minimum qui justifie de passer de l'affinage léger à l'affinage complet

> **Un affinage léger qui ne fait pas passer le webtoon de 5,9 à au moins 12 bulles par bande,
> sans dégrader les deux seuils suivants, n'autorise pas d'affinage complet.**

Le plan du lot 16 formulait ce seuil en « planches webtoon à zéro bulle ». **Ce n'est pas
mesurable sur ce corpus**, et il vaut mieux l'écrire que de fabriquer un chiffre : sur les
9 bandes, **aucune** ne rend zéro bulle. Le défaut du webtoon n'est pas le silence, c'est le
**sous-comptage** — 5,9 bulles par bande de 10 000 px là où une lecture humaine en attend
25 à 35.

12 par bande est donc le doublement du sous-comptage mesuré, et il reste **très en deçà** de ce
qu'une bande porte réellement. Ce n'est pas une cible de qualité, c'est le seuil en dessous
duquel trois semaines de GPU ne se justifient pas.

## Seuil 2 — la baisse minimale du taux de fausses détections sur le webtoon

> **Le taux doit passer sous 8 %.** Au-dessus, l'affinage s'arrête, quel que soit le nombre de
> bulles gagnées.

Référence : **15,1 – 17,0 %**. Le plan du lot 14 visait 5 % et ne l'a pas atteint ; 8 % est la
moitié de la référence, et c'est le seuil retenu ici précisément parce qu'il est **atteignable
et vérifiable**, là où 5 % n'a jamais été autre chose qu'un vœu.

⚠ **Ce seuil prime sur le seuil 1, et l'ordre n'est pas cosmétique.** Un modèle qui trouve plus
de bulles sans faire baisser ce taux n'améliore rien : il aggrave. Chaque fausse détection est
un nettoyage qui abîme la planche, un OCR de bruit, un appel LLM, et **une place numérotée dans
le prompt du traducteur** — puis un dessin recollé par `rendu.restaurer_sans_texte`.

## Seuil 3 — la régression maximale tolérée sur le manga paginé

> **Zéro zone restaurée, zéro bulle sans texte OCR, et pas plus de 1 % de bulles perdues sur les
> 7 803 bulles des neuf volumes paginés.**

Ce seuil est **volontairement presque nul**, et il doit l'être. Le manga paginé est le cas
d'usage établi : neuf volumes de référence, **zéro** zone restaurée, **zéro** bulle sans texte
OCR. Un modèle qui gagne sur le webtoon en perdant sur le manga est un mauvais échange, et il
serait payé par les tomes déjà produits.

Le 1 % de bulles perdues (78 bulles) n'est pas une tolérance de confort : c'est la marge de
l'appariement lui-même, qui compare des masques à IoU ≥ 0,50 et qui compte une bulle
légèrement redécoupée comme perdue.

## Seuil 4 — le budget

> **12 jours de travail et 40 heures de GPU.** Au-delà, on arrête et on publie ce qu'on a.

Le plan du lot 16 estimait 18 jours pour l'ensemble, dont une semaine pour L9.0 seul. Les
12 jours ci-dessus couvrent L9.1 à L9.4 — corpus, affinage léger, éventuel affinage complet,
publication — et **excluent** L9.0, qui est fait.

Ce budget se compte à partir du premier commit de constitution du corpus d'entraînement, et il
se compte en **jours consommés**, pas en jours restants.

---

## Ce qui met fin au lot, dans les deux sens

**Le lot s'arrête et publie un succès** si les seuils 1, 2 et 3 sont tenus ensemble, dans le
budget du seuil 4, et si la licence du poids produit permet la redistribution (cf. L9.4 du
plan : partir d'un poids GPL-3.0 contamine ce qui en découle).

**Le lot s'arrête et publie un échec** — ce qui reste un lot réussi — dès que l'un des cas
suivants se présente :

1. l'affinage léger ne franchit pas le seuil 1 ;
2. le seuil 2 n'est pas atteint alors que le seuil 1 l'est — c'est le cas le plus instructif :
   il dirait que le modèle apprend à voir *plus*, pas à voir *juste* ;
3. le seuil 3 est franchi à la baisse ;
4. le budget du seuil 4 est consommé.

Dans les quatre cas, le résultat va dans `docs/` **avec ses chiffres**, et
`docs/ai-provenance.md` reçoit son entrée. Un résultat négatif documenté évite à quelqu'un
d'autre de refaire le chemin ; un chantier abandonné en silence ne fait qu'attendre d'être
recommencé.

---

## Ce que ces seuils ne couvrent pas, et il faut le dire

- **Le corpus d'entraînement n'est pas contraint par un nombre**, mais par une règle sans
  exception : *toute image utilisée a sa licence écrite dans un fichier du dépôt, et aucune
  œuvre commerciale n'y entre* — ni pour mesurer, ni pour entraîner. La purge des commits
  `86c3d3d` et `b3d1eaa` est un acquis, et Manga109-s est sous conditions d'usage académique.
- **Le corpus de mesure est celui du dépôt**, avec sa faiblesse connue et déjà publiée : **un
  seul** volume webtoon, qui est aussi **le seul** à source latine. Un gain mesuré sur ce seul
  chapitre n'est pas une généralisation, et aucun de ces seuils ne prétend le contraire.
- **Le format de sortie ne se négocie pas ici.** Le post-traitement du dépôt attend un
  YOLOv8-seg à deux têtes (`detection._postprocess`) et un export à **axes dynamiques**
  (`detection.verifier_axe_dynamique`). Changer d'architecture est un autre lot.
- **Un modèle affiné ne devient pas le défaut sans décision explicite** : un tome relancé ne
  produirait plus les mêmes bulles, et neuf volumes de `build/` en dépendent. Il arrive par
  `manga.detection.model_url`, comme une option.
