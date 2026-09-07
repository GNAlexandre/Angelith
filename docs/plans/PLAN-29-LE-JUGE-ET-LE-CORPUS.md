# PLAN 29 — Le juge qui ne sépare pas, et le corpus qui explique peut-être pourquoi

> **Lire `00-CONTEXTE-AGENT.md`, `README-ILLUSTRATION-23-27.md`, puis `README-COMFYUI-28-30.md`.**
>
> **Nature attendue** — **MINEUR**. Un corpus, un protocole, un juge éventuellement remplacé. Ce lot
> peut se conclure par « le juge automatique est inutilisable et on s'en passe » : c'est un résultat,
> et il se publie comme tel.
>
> **Charge estimée** — 12 jours, dont **au moins une demi-journée d'Alexandre**, en aveugle, devant
> des images. Cette demi-journée n'est pas délégable : c'est le seul juge dont le lot 25 ait établi
> qu'il tranche.
>
> **⚠ Se lance sur le PC PRINCIPAL** — il génère.
>
> **⚠ Prérequis : `PLAN-28`.** Sans son validateur, chaque axe du balayage risque une erreur de
> graphe après le déchargement du LLM.

---

## 1. L'état, en trois chiffres

Le lot 25 a livré son juge **étalonné avant d'avoir servi** — c'est la bonne méthode — et
l'étalonnage l'a condamné :

| Ce qui est mesuré | Valeur | Source |
|---|---|---|
| séparations « même personnage » / « personnages différents de la même œuvre » | **68 sur 100** à un seuil de 80 | `docs/mesures/prompt-illustration-2026-08-30.md` §11 |
| protocole humain en aveugle du `PLAN-25` étape 0.3 | **jamais exécuté** | idem |
| personnages du corpus portant **plus d'une** référence validée | **1** | idem, §11.2 |

Conséquence écrite noir sur blanc par le dépôt : **toute colonne « ressemblance » est marquée « non
opposable »**. Et conséquence pratique : *aucune amélioration d'identité ne peut être constatée*. On
ne saurait pas si un changement a aidé.

⚠ **Mais avant d'accuser la métrique, il faut accuser le corpus.** Le lot 25 §8.1 a trouvé, en s'en
servant, que **les trois premières références d'identité validées sont trois couvertures de light
novel, titre de l'œuvre compris, dont deux sont le même dessin**. Un juge à qui l'on demande de
séparer des identités à partir de couvertures — où le personnage est stylisé, en couleur, souvent
accompagné, et surmonté d'un titre typographié — n'a peut-être aucune chance, quelle que soit sa
qualité.

**C'est l'hypothèse que ce lot teste en premier, et l'ordre compte** : changer de métrique avant
d'avoir corrigé le corpus, c'est optimiser un instrument contre un étalon faux.

---

## 2. Étape 0 — trois hypothèses, testées dans cet ordre

### 0.1 — Hypothèse « corpus » : les références ne sont pas des personnages

Prenez les **illustrations intérieures** du tome — celles au trait et en noir et blanc sur
lesquelles la signature de style est mesurée — et produisez, à la main s'il faut, **des recadrages de
personnage** : visage, buste, corps entier, sans titre, sans co-personnage dans le cadre.

Objectif chiffré, et il vient du plan 25 lui-même : **8 personnages, dont au moins 4 avec ≥ 3
références**. Le corpus actuel en porte **1**.

Puis **réétalonnez le juge inchangé** sur ce corpus. Trois issues, et les trois sont des résultats :

| Issue | Ce qu'on en conclut |
|---|---|
| le recouvrement s'effondre, le juge sépare | **le juge n'était pas le problème**, le corpus l'était. Le lot est presque fini, et c'est la meilleure nouvelle possible |
| le recouvrement s'améliore sans suffire | il faut les deux : L29.2 **et** L29.3 |
| rien ne change | la métrique est en cause, ou la tâche n'est pas mesurable ainsi → L29.3, avec un budget borné |

⚠ **Ce n'est pas la même chose que « refaire la bible ».** Le lot 23 a fait son travail : il a
proposé, un humain a validé. Ce que la mesure a montré, c'est que **la classe d'image validée n'était
pas la bonne pour cet usage** — une couverture est une excellente référence de *style*, une mauvaise
référence d'*identité*. La bible porte déjà `role: 'identite' | 'style'` : c'est ce champ qui doit
porter la distinction, pas un second fichier.

### 0.2 — Hypothèse « protocole » : personne n'a encore jugé

Le juge humain en aveugle est **écrit depuis le plan 25 et jamais convoqué**. Il n'est pas un
recours en cas d'échec de l'automatique : il est **l'étalon** de l'automatique. Sans lui, on ne sait
même pas si les 68/100 sont un mauvais score.

**À faire avant tout travail sur la métrique**, parce que c'est lui qui dira ce que la métrique doit
reproduire.

### 0.3 — Hypothèse « métrique » : un encodeur générique ne voit pas l'identité d'un dessin

À n'ouvrir que si 0.1 et 0.2 ne suffisent pas, et avec un **budget borné écrit d'avance** — le dépôt
a le précédent : `docs/mesures/seuils-affinage-detecteur.md` écrit les quatre seuils d'abandon
**avant** de lancer.

Le lot 25 §2.2 a déjà mis **huit prétraitements en concurrence**. Ne les refaites pas. Les pistes qui
restent, par coût croissant :

1. **juger sur le recadrage, pas sur l'image entière** — si l'image générée est comparée en pleine
   page à un recadrage de visage, la moitié du signal est du décor ;
2. **juger par attributs mesurables** plutôt que par embedding : la couleur de cheveux, le régime de
   couleur, la présence d'un signe distinctif se mesurent en numpy et **se disent** — et un verdict
   qui nomme sa raison vaut mieux qu'un cosinus ;
3. **un encodeur entraîné sur du dessin** plutôt que sur de la photo. ⚠ Licence des **poids** à
   vérifier à la source primaire, jurisprudence du dépôt (`docs/mesures/detecteurs-candidats-2026-08-26.md`,
   les poids de LaMa jamais établis).

---

## L29.1 — Le corpus, et il se construit avec l'outil existant

`tools/bible.py --revue` sait déjà présenter et valider. Ce qu'il faut ajouter est minime :

- **le rôle demandé** : `--role identite` ne propose que des candidates plausibles pour l'identité
  et **repousse les couvertures en dernier** — le lot 26 le fait déjà pour `retenir`, appliquez la
  même règle à la revue ;
- **le recadrage assisté** : sur une illustration intérieure, proposer le rectangle et laisser
  l'humain l'ajuster. Pas de détection de visage, pas d'OpenCV (interdit n° 4) : un rectangle
  proposé, un rectangle corrigé ;
- **le compte visible** : combien de personnages ont 0, 1, 2, ≥ 3 références de rôle `identite`.
  C'est le tableau qui dit quand le corpus est prêt, et il doit s'afficher à chaque revue.

⚠ **Ne jetez pas les couvertures.** Elles restent d'excellentes ancres de **style**, et le lot 26 a
montré que le registre se corrige aussi par les mots. Changez leur `role`, ne les supprimez pas.

## L29.2 — Le protocole en aveugle, exécuté pour de vrai

Un outil, le plus bête possible, parce que sa valeur est dans la discipline et pas dans le code :

```powershell
python tools/juge_humain.py --paires 20      # présente (référence, A, B) sans étiquette, note la réponse
python tools/juge_humain.py --rapport        # le tableau, l'accord avec le juge automatique
```

**Trois règles, et la première est celle qu'on viole toujours :**

1. **le seuil de succès est fixé avant de voir les résultats.** Le plan 25 proposait : préférée dans
   au moins **14 cas sur 20**. Gardez-le, ou changez-le **maintenant**, pas après ;
2. **l'ordre A/B est tiré au sort et l'étiquette est cachée**, y compris dans le nom du fichier
   temporaire — un dossier trié par date suffit à trahir la configuration ;
3. **les réponses sont horodatées et conservées.** Un protocole en aveugle non archivé n'est pas
   reproductible, et c'est le seul juge opposable du dossier.

**Le produit de cette étape n'est pas un verdict, c'est un étalon** : l'accord entre le juge humain et
le juge automatique, sur les mêmes 20 paires. C'est ce chiffre — et pas les 68/100 — qui dit si
l'automatique est utilisable.

## L29.3 — Le juge, seulement s'il le faut

Si l'étape 0.1 a suffi, **écrivez que L29.3 n'a pas été ouverte et pourquoi**. C'est une information
utile pour dans six mois.

Sinon, une piste à la fois, chacune évaluée sur **le même** protocole en aveugle comme étalon, et le
tableau publié même quand la piste perd. Le critère de réussite n'est pas « un meilleur cosinus » :
c'est **le recouvrement**, la seule question que le lot 25 §2.4 a identifiée comme la vraie.

## L29.4 — Les deux descripteurs qui restent faux, et l'un est de notre faute

Le registre est « nettement amélioré, pas réglé ». Deux écarts subsistent, et ils ne se traitent pas
pareil :

| Descripteur | Généré | Tome | Cause identifiée |
|---|---:|---:|---|
| densité de trait | 0,1188 | **0,2664** | le conditionnement suit le registre des **références** ; des références au trait devraient l'améliorer → c'est L29.1, gratuitement |
| part d'aplats | 0,6300 | **0,3669** | ⚠ **le prompt lui-même** : « sur fond neutre » demande une grande surface d'une seule teinte, et le tome n'en a pas autant |

**La part d'aplats est une régression que le dépôt a introduite**, pas une limite du modèle. Testez
la retirer, ou la remplacer par un fond décrit dans le registre du tome (hachures, trame, décor
sommaire). Un mot du gabarit contre deux points de descripteur : c'est le meilleur rapport de la
série, et il se mesure en trois images.

⚠ **Mesurez les deux séparément.** Une amélioration moyenne qui cache une régression sur un
descripteur est exactement ce que le critère 4 ter du plan 25 interdit de moyenner.

## L29.5 — Les dénominateurs, enfin

Le plan 26 §11.2 écrit : « le plan demande 8 personnages et 10 images par axe ; les axes qui génèrent
ont tourné sur **un personnage** et **2 à 3 images par axe** ». À 103,7 s par image en
texte-vers-image et 233,7 s en édition, 8 personnages × 10 images en édition coûtent environ
**5 h 12 de GPU** — c'est un run de nuit, mécanisme que le dépôt possède déjà (`--keep-awake`,
checkpoints, reprise).

**Publiez le coût avant de lancer, et lancez.** Un plan qui réclame des dénominateurs depuis deux
lots sans jamais payer les heures qu'ils coûtent finit par accepter des chiffres sur trois images.

---

## 3. Les critères de ce lot

1. Le corpus porte **8 personnages**, dont ≥ 4 avec ≥ 3 références de rôle `identite`, **aucune
   couverture** parmi elles. Le tableau 0/1/2/≥3 est publié avant et après.
2. Le juge **inchangé** est réétalonné sur ce corpus, et le nouveau recouvrement est publié à côté de
   l'ancien (68/100 à seuil 80).
3. Le protocole en aveugle est **exécuté** — 20 paires, seuil fixé d'avance, réponses archivées — et
   l'**accord humain/automatique** est publié. C'est le livrable central du lot.
4. Le verdict d'identité est **tranché** : la voie A tient, ou elle ne tient pas. Si le juge
   automatique reste inutilisable, il est déclaré tel et les colonnes « ressemblance » du dépôt sont
   étiquetées d'après le juge humain, pas d'après lui.
5. La part d'aplats est mesurée **avec et sans** « fond neutre » dans le gabarit, et le gabarit retenu
   est celui que la mesure désigne.
6. La densité de trait est publiée sur le nouveau corpus. Si des références au trait la rapprochent
   des 0,2664 du tome, dites de combien ; si elles ne changent rien, dites-le aussi.
7. Chaque axe qui génère porte son **dénominateur réel**, et le coût GPU du lot est publié.
8. `ruff check .` passe ; `pytest -q -m "not modeles and not lent"` passe sans serveur ni GPU.
9. `docs/mesures/identite-<date>.md` reprend ces critères un par un, y compris les non tenus, et dit
   ce que la mesure ne dit pas.

## 4. Ce que ce lot ne fait pas

- Il n'ouvre pas la voie B (LoRA par personnage). Le lot 25 a conclu qu'elle n'avait pas à l'être, et
  rien ici ne renverse cette conclusion.
- Il n'installe aucun canal structuré : c'est le `PLAN-30`.
- Il ne touche pas à l'interface : c'est le `PLAN-27`.
- Il ne réécrit pas la bible du lot 23. Il en corrige **un champ** — `role` — et ajoute des
  recadrages là où il n'y avait que des couvertures.
