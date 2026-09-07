# Le banc de mesure

Ce document décrit **comment le projet mesure sa brique manga**, avec quelle commande, sur quel
corpus, sous quelles licences — comme [`ai-provenance.md`](../ai-provenance.md) le fait déjà pour
les modèles.

Il n'améliore rien. Il rend les améliorations visibles, et — ce qui est moins confortable — il
rend visibles celles qui n'en sont pas.

---

## 1. Les commandes

```powershell
# Le tableau de détection, tous les volumes de build/, daté et signé du commit
python tools/banc.py --tous --markdown > docs/mesures/banc-2026-08-25.md

# Un seul volume
python tools/banc.py "Mon Oeuvre" Vol.2

# Le banc de traduction — aucun appel LLM
python tools/banc.py --tous --traduction --markdown

# Rappel / precision / F1 contre le corpus annote (charge le detecteur)
python tools/banc.py --corpus tests/corpus/synthetique --markdown

# Pour tracer une courbe
python tools/banc.py --tous --json

# Balayer les RÉSOLUTIONS d'entrée sur une planche — le levier du lot 12
python tools/apercu_detection.py "Mon Oeuvre" Vol.2 --page 57 --resolutions --balayage

# Comparer un détecteur CANDIDAT à celui du dépôt, à armes égales — le lot 16
python tools/banc_candidats.py --tous --sur-zero --actuel --yolo poids/candidat.onnx --markdown
```

> **La seconde exception, ajoutée au lot 16.** `tools/banc_candidats.py` charge des modèles —
> il n'y a pas d'autre façon de mesurer un détecteur qui n'a jamais tourné sur le corpus. Il
> n'écrit toujours rien sous `build/`, et il applique à **tous** les bras la scission et le
> rendu disjoint du pipeline : sans cela un candidat afficherait mécaniquement moins de bulles
> que le détecteur en place, et l'écart mesuré serait celui du post-traitement. Le contrôle qui
> le prouve : `--actuel` recompte **exactement les 53 bulles** publiées sur les 9 bandes du
> webtoon. Résultat de sa première campagne :
> [`detecteurs-candidats-2026-08-26.md`](../mesures/detecteurs-candidats-2026-08-26.md).

`tools/banc.py` lit **uniquement** les caches sous `build/` : aucun modèle chargé, rien de
réécrit, et il se lance pendant qu'un run tourne. `--corpus` est la seule exception, et elle
est assumée : mesurer un rappel demande de détecter.

> **Une entorse en lecture, ajoutée au lot 12.** Pour la colonne « dont encrées » seulement, le
> banc consulte `sources/` en dernier recours, après `pages_out/` et `pages_clean/`. Sans elle,
> les **43 planches** à zéro bulle des deux premiers volumes de *manga D* — qui n'ont
> ni rendu, ni page nettoyée, ni `qa.json` — restaient définitivement **non mesurables**, et
> une case vide dans une colonne de nombres se lit comme un zéro. Rien n'est écrit, et
> `sources/` absent ramène simplement la colonne à « non mesurée ».

### ⚠ Les seuils sont gratuits, la résolution ne l'est pas

`conf_threshold` et `iou_threshold` ne servent **qu'au post-traitement** : douze réglages
coûtent une inférence et douze post-traitements. `input_size`, lui, change le tenseur d'entrée
— chaque valeur **repaie l'inférence**, une par fenêtre sur une bande découpée.

C'est pour cela que `--resolutions` est un drapeau à part et non une colonne de plus du
balayage, et que le temps par résolution est affiché à côté du résultat : l'arbitrage
coût/gain doit se faire sur des chiffres. Et c'est aussi pourquoi la résolution relevée est,
dans la configuration livrée, réservée aux planches **suspectes**
(`manga.detection.escalade.input_size`) plutôt qu'appliquée au tome entier
(`manga.detection.input_size`, qui reste à 640).

Chaque sortie `--markdown` porte **la date, le commit, la version du dépôt et l'empreinte
SHA-256 de `config.yaml`**. Deux tableaux ne se comparent que si l'on sait ce qui a changé entre
eux : le code, la configuration, ou le corpus.

---

## 2. Ce qui est mesuré, et laquelle des métriques décide

Rappel, précision et F1 sont publiés parce qu'ils sont attendus. Mais **la métrique qui
décide n'est aucune des trois** :

> **le nombre de planches portant du texte et rendant zéro bulle.**

Une planche à 60 % de rappel produit un résultat imparfait qu'un relecteur corrige ; une
planche à zéro produit une page **entièrement non traduite** que personne ne voit passer. Une
moyenne de F1 les confond.

Et à côté d'elle, promue au même rang par la mesure du webtoon :

> **le taux de fausses détections par planche.**

`geometry.py` revendique zéro faux positif, et c'est vrai sur le manga paginé : **zéro zone
restaurée sur les 7 803 bulles** des neuf volumes paginés. Sur le seul webtoon du corpus,
**13 des 59 bulles** en sont (22 %). Le rapport produit **trois** indicateurs distincts, à
publier tous les trois parce qu'ils ne mesurent pas la même chose :

| Indicateur | Source | Ce qu'il dit |
|---|---|---|
| zones **restaurées** | `qa["restaurees"]`, cf. `rendu.restaurer_sans_texte` | ni texte source ni réplique : le dessin d'origine a été recollé |
| bulles **sans texte OCR** | `qa.json` | la zone a été détectée et nettoyée, l'OCR n'y a rien lu |
| bulles **non nettoyées** | `qa.json`, uniformité < `nettoyage.seuil_abandon` | le nettoyage lui-même a renoncé |

**Un lot qui gagne des bulles sans republier ces trois chiffres peut dégrader le résultat en
affichant un succès.**

> ⚠ **Le dénominateur du webtoon a bougé, et il vaut la peine de dire pourquoi.** Ce document
> a d'abord annoncé « 11 des 59 ». Le bon chiffre est **13 des 59**, mesuré sur
> `ocr.json` + `traduction.json` plutôt que sur `qa.json` : les deux planches du chapitre qui
> n'ont pas de `qa.json` échappaient au décompte, alors que leurs textes sont bien en cache et
> alignés par position sur `regions.json`. C'est exactement le piège n° 1 de `tools/banc.py`,
> qui s'est retourné contre ce paragraphe-ci. La mesure complète est dans
> [`webtoon-2026-08-26.md`](../mesures/webtoon-2026-08-26.md), où le taux tombe à **15,1–17,0 %**.

### La quatrième mesure : la MÉMOIRE

Elle est arrivée en 2.6.0, et elle est d'une autre nature — c'est la seule ligne du rapport qui
décrit la **machine** et non le tome. Un contributeur dont le run se fait tuer sur un webtoon
n'avait jusque-là rien à joindre à son ticket.

`perf.log` porte le pic **en différentiel** autour de chaque passe visuelle (le pic du processus
est monotone : l'attribuer en bloc ferait porter à la première planche la mémoire de tout ce qui
l'a précédée), `RAPPORT.md` porte le pic du run entier. Aucune dépendance nouvelle : `kernel32`
par `ctypes` sous Windows, `/proc/self/status` sous Linux, `getrusage` ailleurs — et `?` quand
le système ne sait pas répondre, jamais un zéro inventé.

Repères mesurés sur une bande de 1080×10 000 : **637 Mo** pour la détection seule, **1,36 à
1,73 Go** avec la passe hors bulle — dont **+685 Mo pour une seule inférence** du détecteur de
texte, qui est de très loin le poste dominant.

### Publié avec elles

- la distribution du rappel **par taille de bulle** — c'est là que se voit le gain
  d'`input_size` ;
- le compte de **doubles non scindées**, contre l'annotation ;
- le même tableau **séparément pour manga paginé et pour webtoon**. Deux régimes différents,
  qu'une moyenne unique masquerait — et l'écart mesuré, de 0 % à 19 % de zones restaurées
  selon le format, suffit à le prouver ;
- une colonne **langue source**. Le seul volume webtoon du corpus est aussi le seul à source
  latine (`ocr_latin.py` au lieu de `manga-ocr`) : sans cette colonne, le banc confondrait un
  effet de **format** avec un effet d'**OCR**. Le banc l'infère de l'OCR en cache, faute de la
  trouver ailleurs ; ajouter au corpus un volume qui sépare les deux — un manga paginé à source
  latine, ou un webtoon en japonais — reste la première chose à faire.

### L'appariement

⚠ `detection_retry.apparier`, et **pas** une réimplémentation. Glouton, à IoU de masques
≥ 0,50, et son argument est le bon : « une bulle conservée est la même bulle, pas une bulle au
même endroit ». Deux implémentations mesureraient deux choses.

---

## 3. Le corpus

### Le corpus synthétique — redistribuable sans réserve

`tests/corpus/synthetique/`, produit par
[`tools/corpus_synthetique.py`](../../tools/corpus_synthetique.py) à graine **figée et publiée**
(`GRAINE = 20260825`). Trois planches, 22 bulles annotées :

| Planche | Ce qu'elle piège |
|---|---|
| `page_manga_01.png` (1200×1800) | bulle ordinaire, **minuscule** (≈ 44×30 px), ballon de **cri**, **récitatif** rectangulaire, **double collé**, bulle **à cheval** sur un trait de case |
| `page_manga_02.png` (1200×1800) | les mêmes, sur un fond de **trame** — `clean.py` choisit son mode d'après l'uniformité de la zone |
| `bande_webtoon_01.png` (**1080×10 000**) | le **découpage en fenêtres** : sans lui une bulle de webtoon arrive au réseau en 26×32 px et n'est pas émise |

**Licence : AGPL-3.0-or-later**, celle du dépôt. Tout est généré par le fichier qui le décrit :
aucune œuvre, aucun scan, aucun poids de modèle n'y entre. La licence est écrite dans
`info.licence` de l'`annotations.json` lui-même — un corpus dont la licence n'est pas dans le
fichier n'est pas redistribuable en pratique.

### Ce qui n'entre pas dans le corpus, et pourquoi

| Voie | Statut |
|---|---|
| Œuvres commerciales | **Purgées du dépôt une fois pour toutes** (`86c3d3d`, `b3d1eaa`). Elles ne reviennent pas, même pour mesurer. |
| **Manga109-s** | Conditions d'usage **académique**. Le dépôt le signale déjà (`manga/models.py`, `manga_models/README.md`). Les poids de recherche ont la même restriction. |
| Œuvres sous licence libre | **La voie à suivre**, et la seule qui produise un banc reproductible par un tiers. Rien n'est promis sur une taille de corpus avant d'avoir cherché ce qui existe. |
| Corpus privé, chiffres publics | Honnête **si c'est dit**, non reproductible. À réserver au complément. |

### Le format d'annotation

**COCO instance segmentation** — celui que tout outil d'annotation exporte. Aucun format n'a
été inventé. Un `annotations.json` par corpus, les images à côté ; la conversion se fait à la
lecture (`_banc_detection.regions_de_verite`).

`_banc_detection.ecrire_cache_verite` écrit en plus la même vérité **au format du pipeline**
(`regions.json` + `masks.png`), pour que la comparaison soit directe et que la vérité terrain
se relise avec les outils habituels du dépôt. Une vérité terrain qu'on ne peut pas ouvrir n'est
vérifiée par personne.

---

## 4. Le banc de traduction

Huit lignes visées, **calculables sur les caches existants sans un seul appel LLM**. Cinq sont
dans `python tools/banc.py --tous --traduction` :

| Mesure | Source | État |
|---|---|---|
| bulles vides à l'arrivée | `qa.json` / `traduction.json` | ✅ |
| motifs d'échec résiduels, par motif | `qa.json`, cf. `quality_manga.MOTIFS` | ✅ |
| stratégie de rattachement (numérotée / positionnelle) | `qa.json`, `strategie_traduction` | ✅ |
| rattrapages unitaires | `qa.json`, `rattrapee` | ✅ (le **taux de rejet** n'est pas persisté : `qa.json` retient la bulle rattrapée, pas les tentatives que `quality_manga.diagnostiquer_rattrapage` a refusées) |
| longueur rendue / longueur source | `qa.json` | ✅ médiane |
| formes bannies subsistantes | [`tools/compter_variantes.py`](../../tools/compter_variantes.py) | ✅, **outil séparé** — il lui faut le glossaire de l'œuvre, donc `sources/`, que le banc n'exige pas |
| termes du glossaire présents dans la source, absents du rendu | — | ⏳ lot 15 |
| basculements de registre | — | ⏳ lot 15 |

### La part irréductible de jugement

La fidélité et le naturel d'une réplique ne se mesurent pas sans lecteur. Protocole minimal et
honnête, quand il faudra en passer par là :

- un échantillon **figé et publié** (100 bulles, graine écrite dans le dépôt) ;
- une relecture **à l'aveugle** — les deux versions, sans dire laquelle est laquelle ;
- **trois questions fermées** (le sens est-il juste, la longueur tient-elle, le registre est-il
  cohérent avec la fiche) plutôt qu'une note globale, qui ne se compare pas d'une session à
  l'autre.

⚠ Un juge unique qui est aussi l'auteur du changement **n'est pas une mesure**. C'est un
garde-fou, et il faut l'écrire comme tel.

**À ne pas faire :** une métrique automatique de similarité à une traduction de référence. Sur
des répliques de bulle, courtes et idiomatiques, elle punit les bonnes traductions qui diffèrent
de la référence et récompense les paraphrases plates.

---

## 5. La non-régression en intégration continue

`tests/test_banc_corpus_synthetique.py` fait tourner le banc sur le **corpus synthétique seul**
— le seul qui soit commitable — et **casse le build si le rappel baisse ou si les faux positifs
montent**. Les deux, et pas seulement le premier : un lot qui gagne des bulles en gagnant autant
de fausses détections n'améliore rien.

Une régression de détection est ainsi attrapée par un `git push`, pas par un tome raté trois
semaines plus tard.

La ligne de base vit dans `tests/corpus/synthetique/reference.json` et **se recalibre à la
main** — un banc qui réécrit sa propre référence à chaque run ne mesure plus rien :

```powershell
python tools/banc.py --corpus tests/corpus/synthetique --json > tests/corpus/synthetique/reference.json
```

Le diff de ce fichier est ce qu'on relit en revue.

---

## 6. Ce que la publication change

1. **Une amélioration devient citable.** « La détection est meilleure » ne se défend pas.
   « *N* planches à zéro bulle sur les *M* du corpus avant, *N'* après, protocole et corpus
   publiés, reproductible en une commande » se défend.
2. **Une comparaison devient possible** — deux jeux de poids, un modèle affiné, sur le même
   terrain. C'est ce qui empêche d'ajouter 100 Mo de poids sur une intuition.
3. **Une régression devient impossible à ignorer.**

---

## Voir aussi

- [`chiffres-de-reference.md`](../chiffres-de-reference.md) — ce que compte chaque nombre du
  projet, et avec quelle commande le refaire.
- [`ai-provenance.md`](../ai-provenance.md) — les modèles, leur provenance et leurs licences.
- [`banc-2026-08-25.md`](../mesures/banc-2026-08-25.md) — le tableau **« avant »** du lot 10 : dix
  volumes, 1 513 planches, 7 862 bulles, et les trois écarts avec les `RAPPORT.md` expliqués.
