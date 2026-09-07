# PLAN 25 — L'identité tient ou ne tient pas, et on le mesure

> **Lire `00-CONTEXTE-AGENT.md` puis `README-ILLUSTRATION-23-27.md` d'abord.**
>
> **Nature attendue** — **MINEUR**. Nouvelle capacité, opt-in, défaut inchangé. Un réglage qui ne se
> justifie pas se livre **désarmé**.
>
> **Charge estimée** — 15 jours, dont une part de R&D au résultat incertain (14 + 1 pour l'échelle
> de style, ajoutée le 2026-08-27).
>
> **⚠ Prérequis absolus : `PLAN-23` et `PLAN-24`.** Sans bible validée par un humain, il n'y a pas de
> référence ; sans socle mesuré, il n'y a pas de moteur.
>
> **C'est le seul plan de la série qui peut légitimement se conclure par « on ne le fait pas », et
> cette conclusion doit être publiée comme un résultat.** Le dépôt a déjà ce précédent : L6.2 a été
> **refusé sur mesure**, et `docs/mesures/webtoon-2026-08-26.md` a livré trois réglages désarmés.

---

## 1. Le problème, énoncé sans marketing

« Créer des images inédites et cohérentes sur une œuvre avec le bon personnage » se décompose en
trois exigences de difficulté très inégale :

| Exigence | Difficulté | Qui la traite |
|---|---|---|
| l'image est belle et propre | faible — c'est le métier du modèle | `PLAN-24` |
| l'image respecte les attributs écrits (cheveux noirs, uniforme, adolescente) | moyenne — c'est du prompt | `PLAN-26` |
| **le personnage est reconnaissable comme *le même* d'une image à l'autre** | **c'est le problème** | ce plan |

La troisième n'est pas une affaire de prompt. Deux images générées depuis la même description
textuelle produisent deux personnes différentes qui respectent toutes deux la description. C'est
exactement l'écart entre « illustration plausible » et « illustration de cette œuvre ».

**Deux familles de solutions, et il faut mesurer laquelle marche ici, pas laquelle marche en
général.**

| Voie | Principe | Coût | Risque |
|---|---|---|---|
| **A — conditionnement par référence** | `Qwen-Image-Edit-2511` accepte plusieurs images de référence et annonce « character consistency significantly improved » | zéro entraînement, quelques secondes de plus par image | dépend entièrement de la qualité des recadrages de la bible |
| **B — LoRA par personnage** | un petit adaptateur entraîné sur les recadrages d'un personnage | heures de GPU par personnage, et une décision juridique | **entraîner sur un corpus sous droits est une décision d'Alexandre, pas de l'agent** |

⚠ **La voie B ne s'ouvre pas par défaut.** Elle transforme des images sous droits en poids de
modèle. L'usage est privé (§1 du README de série), ce qui est le cas le plus favorable, mais la
décision doit être écrite dans `docs/ai-provenance.md` **avant** le premier entraînement, avec la
raison. Et le poids produit ne quitte jamais la machine : il n'est ni committé, ni publié, ni
partagé — ajoutez son motif au `.gitignore` dans le même commit.

**L'ordre est donc : A d'abord, entièrement mesurée. B seulement si A échoue, et seulement après
décision écrite.** Une voie B lancée avant d'avoir mesuré A, c'est trois semaines de GPU pour ne pas
savoir si elles étaient nécessaires — précisément ce que `docs/mesures/seuils-affinage-detecteur.md` a
refusé pour le détecteur de bulles.

---

## 2. Étape 0 — le protocole de mesure, avant la première génération

**Rien ne se mesure sans un juge, et un juge n'est ni « ça a l'air bien » ni un score qu'on n'a pas
étalonné.** Cette étape construit le juge, et elle vient avant tout résultat.

### 0.1 — Le corpus d'évaluation

- **8 personnages** au minimum, tirés de la bible et **validés par un humain**, dont au moins 2 avec
  une seule image de référence et au moins 2 avec trois ou plus. La distribution compte autant que
  la moyenne : un personnage à une seule référence est le cas réel majoritaire.
- **Le seul personnage dont une image peut figurer dans le document de mesure vient de
  `Pride and Prejudice`** (domaine public, 164 fichiers dans son `media/`). Pour tous les autres,
  le document publie des **chiffres**. Si `Pride and Prejudice` n'a aucun personnage utilisable —
  son glossaire déclare **0 personnage** au 2026-08-27 —, il faut d'abord en construire la bible
  (`PLAN-23` sur ce projet), ou le document de mesure sera **sans aucune image**. Dites-le, ne le
  contournez pas.

### 0.2 — Le juge automatique, et ses limites écrites d'avance

Une distance d'apparence entre l'image générée et les références, calculée par un encodeur d'image
**ONNX** — `onnxruntime` est déjà une dépendance de `requirements-manga.txt` et c'est le seul moteur
d'inférence que le dépôt accepte. Un encodeur d'image de type CLIP ou DINOv2 en ONNX pèse de l'ordre
de 100 à 350 Mo, ce qui est du même ordre que le détecteur déjà téléchargé (104 Mo).

⚠ **Pas d'OpenCV** (interdit n° 4) et **pas de `torch`** pour ça : un cosinus entre deux vecteurs
s'écrit en numpy.

**Étalonnez le juge avant de l'utiliser** — c'est la partie que tout le monde saute :

| Paire | Ce que la distance devrait donner | Pourquoi c'est nécessaire |
|---|---|---|
| deux références **du même** personnage | plancher haut de similarité | donne le maximum atteignable |
| références de **deux personnages différents** de la même œuvre | plancher bas | donne le seuil de confusion — et il sera plus haut qu'attendu, car ils partagent le style de dessin |
| une référence contre une image d'une **autre œuvre** | plus bas encore | contrôle négatif |
| deux illustrations **quelconques du même tome**, personnages différents | **l'échelle de STYLE** : ce que « appartenir au même tome » vaut, indépendamment du sujet | c'est ce plancher qui dit si une image générée est dans le registre du tome |
| une illustration du tome contre une illustration d'un tome d'une **autre œuvre** | plancher bas de style | donne la largeur de l'échelle de style |

⚠ **Les deux dernières lignes mesurent une autre chose que les trois premières**, et il ne faut pas
les confondre : les trois premières situent **l'identité** (est-ce la même personne ?), les deux
dernières situent le **registre graphique** (est-ce le même dessinateur ?). Le fait que deux
personnages différents d'un même tome se ressemblent « plus qu'attendu » — noté ci-dessus comme un
inconvénient pour l'identité — est exactement le **signal utile** pour le style. Une seule métrique
sert aux deux, avec deux échelles distinctes : nommez-les, ne les mélangez pas.

**Sans ces cinq planchers, un cosinus de 0,78 ne veut rien dire.** Publiez-les. Si l'écart entre
« même personnage » et « personnages différents de la même œuvre » est inférieur à ce que le bruit
de mesure justifie, **le juge automatique est inutilisable** : dites-le et passez au seul juge
humain.

### 0.3 — Le juge humain, en aveugle

20 triplets `(référence, image A, image B)` où A et B viennent de deux configurations différentes,
présentés **sans étiquette**, et Alexandre désigne laquelle ressemble le plus au personnage. C'est
lent, c'est irremplaçable, et c'est le seul verdict qui compte pour la question posée.

Fixez **d'avance** le seuil de succès du lot. Proposition, à valider :

> Une configuration est retenue si, sur 20 comparaisons en aveugle, elle est préférée dans au moins
> **14** cas (70 %) **et** si le cosinus médian « généré contre référence » se situe au-dessus de la
> moitié de l'intervalle entre le plancher de confusion et le plancher haut de l'étape 0.2.

Un seuil fixé après avoir vu les résultats n'est pas un seuil.

---

## L25.1 — La voie A, conditionnement par référence

`illustration/identite.py` : construire la requête de `Qwen-Image-Edit-2511` à partir des
`references[]` de la bible — recadrages validés, redimensionnés au ratio du modèle, au plus N images.

**Les paramètres à balayer, un seul à la fois** (le dépôt a déjà cette discipline dans
`tools/apercu_detection.py --balayage`) :

1. **nombre de références** : 1, 2, 3, et le maximum accepté. La question réelle : est-ce que la
   3ᵉ référence améliore, ou est-ce qu'elle moyenne le personnage jusqu'à le rendre générique ?
2. **nature du recadrage** : visage seul, buste, corps entier. Publiez la comparaison — c'est le
   chiffre qui dit ce que `PLAN-23` L23.5 doit demander à l'utilisateur de recadrer.
3. **force de conditionnement / guidage**, sur trois valeurs. Trop haut : l'image est un décalque de
   la référence, ce qui n'est plus « inédit ». Trop bas : ce n'est plus le personnage. **Mesurez les
   deux échecs séparément** : une distance qui monte peut signifier « ressemblance perdue » ou
   « décalque » — deux défauts opposés que la même métrique confond.

⚠ **Trois grandeurs se mesurent sur chaque image générée, pas une.** Les confondre est l'erreur
qui rend un balayage illisible :

| Grandeur | Contre quoi | Ce qu'un mauvais score veut dire |
|---|---|---|
| **ressemblance** | les références d'identité du personnage | ce n'est pas lui |
| **nouveauté** | la référence la **plus proche** | c'est un décalque de la référence |
| **style** | la `signature` et les `ancrages` du tome (`PLAN-23` L23.7) | c'est lui, c'est inédit, et ça ne va pas avec le tome |

**La troisième est celle qui répond à « pas trop loin des images précédentes »**, et c'est la seule
que ni la ressemblance ni la nouveauté ne peuvent attraper : une image peut être parfaite sur les
deux premières et sortir un rendu 3D là où le tome est au trait. Mesurez-la sur les deux échelles :
la distance d'embedding **et** l'écart des descripteurs déterministes (palette, saturation,
contraste, densité de trait, part d'aplats). Les deux, parce qu'un embedding capte le « genre
d'image » et les descripteurs captent ce qui se voit au premier coup d'œil.

⚠ **La mesure de nouveauté**, elle, empêche d'optimiser vers la copie : distance entre l'image
générée et la référence la **plus proche**. Une image excellente en ressemblance et à distance quasi
nulle de sa référence n'est pas une illustration inédite, c'est une reproduction — et pour une œuvre
sous droits, c'est aussi le pire cas juridique. **Un plancher de nouveauté est un garde-fou, pas un
raffinement.**

## L25.2 — Le garde-fou de refus

Sur le modèle du refus d'accord incertain de `manga/relecture.py` et du mode `"rapport"` des
onomatopées : **la brique doit savoir refuser.**

- moins d'une référence validée par un humain pour ce personnage → **refus**, message explicite, pas
  de génération « au mieux » ;
- cosinus de l'image produite sous le plancher de confusion de l'étape 0.2 → l'image est produite
  mais **marquée `ressemblance: faible`** dans son sidecar de provenance, et l'atelier du `PLAN-27`
  la présente comme telle ;
- **distance de style hors de l'échelle du tome** → l'image est produite et marquée
  `style: hors_registre`, avec **quel descripteur a décroché** (« saturation 2,4× la signature »,
  « densité de trait 0,3× ») — un motif nommé vaut mieux qu'un score, parce qu'il dit quoi corriger
  dans la requête ;
- distance de nouveauté sous le plancher → l'image est **rejetée**, avec son motif. Ce cas n'est pas
  négociable.

Les motifs d'échec suivent la convention du dépôt : nommés, comptés, et remontés dans le rapport
(`manga/detection_retry.py` en donne le modèle avec ses libellés lisibles).

## L25.3 — La voie B, et seulement si A a échoué

À n'ouvrir que si L25.1 conclut, chiffres à l'appui, que le conditionnement ne tient pas. Alors :

1. **La décision écrite d'abord** (§1 de ce plan), dans `docs/ai-provenance.md`.
2. Les quatre seuils d'abandon **écrits avant de lancer**, comme `docs/mesures/seuils-affinage-detecteur.md`
   l'a fait pour le détecteur : nombre de références minimum sous lequel on n'entraîne pas, heures de
   GPU au-delà desquelles on arrête, gain minimal attendu sur le juge de l'étape 0.2, et taux de
   surapprentissage au-delà duquel le résultat est un décalque.
3. **Un seul personnage** en premier, celui qui a le plus de références. Pas huit.
4. Le poids reste local, gitignoré, et son existence est déclarée dans le sidecar de chaque image
   qu'il produit.

Si la mesure de A suffit, **écrivez que la voie B n'a pas été ouverte et pourquoi**. C'est une
information utile pour la personne qui reprendra le sujet dans six mois.

## L25.4 — Le banc, reproductible

`tools/banc_identite.py`, dans l'esprit de `tools/banc.py` et `tools/banc_candidats.py` :

```powershell
python tools/banc_identite.py --etalonnage                     # les trois planchers de l'étape 0.2
python tools/banc_identite.py --personnage "<nom>" --balayage  # L25.1
python tools/banc_identite.py --tous --markdown > docs/identite-<date>.md
```

Le tableau porte la date, le commit, l'empreinte SHA-256 de `config.yaml`, le modèle et l'empreinte
de ses poids. Il tourne avec `MoteurFactice` en CI (donc testable sans GPU) et avec le vrai moteur à
la main, sous marqueur `modeles` et `lent`.

---

## 3. Les critères de ce lot

1. Les **trois planchers** du juge sont publiés. Si le juge est inutilisable, c'est écrit et le lot
   repose sur le seul juge humain.
2. Le protocole en aveugle (20 comparaisons) a été **exécuté par un humain**, et son seuil était
   fixé avant les résultats.
3. Le balayage de L25.1 est publié : nombre de références, nature du recadrage, force de
   conditionnement — un paramètre à la fois, avec le tableau complet, y compris les configurations
   perdantes.
4. La **mesure de nouveauté** existe et son plancher est armé. Une image trop proche d'une référence
   est rejetée, et un test le prouve.
4 bis. La **mesure de style** existe, sur les deux échelles (embedding et descripteurs), et son
   verdict nomme le descripteur qui décroche. Elle est livrée **armée en signalement** ; un rejet
   automatique sur le style n'est armé que si la mesure le soutient — sinon, livrez-le désarmé et
   écrivez pourquoi.
4 ter. Le balayage de L25.1 publie les **trois** grandeurs côte à côte pour chaque configuration.
   Une configuration qui gagne en ressemblance et perd en style est un fait à montrer, pas à
   moyenner.
5. Le refus fonctionne : un personnage sans référence validée ne produit **aucune** image.
6. Verdict explicite : la voie A est retenue, ou elle est refusée sur mesure. Si elle est refusée,
   la voie B est ouverte **avec sa décision écrite**, ou la série s'arrête ici — et le document le
   dit.
7. `ruff check .` passe ; `pytest -q -m "not modeles and not lent"` passe sans poids ni GPU.
8. `docs/identite-<date>.md` reprend ces critères un par un, **y compris les non tenus**, et publie
   ce que la mesure ne dit pas — au minimum : sur combien de personnages, avec combien de
   références, et ce qui se passe pour un personnage secondaire qui n'apparaît que dans une image de
   groupe.

## 4. Le résultat négatif est un résultat

Si, au terme des 14 jours, l'identité ne tient pas — le juge ne discrimine pas, le protocole en
aveugle donne 11/20, la nouveauté et la ressemblance ne peuvent pas être satisfaites ensemble —
alors le lot livre : le banc, les planchers, le garde-fou de refus, et un document qui dit
**pourquoi**. Les `PLAN-26` et `27` sont alors abandonnés, pas repoussés, et le `PLAN-23` reste
acquis avec son gain de genre sur 150 personnages.

**« Un tableau qui ne confirme jamais que le plan n'est pas une mesure »** — `00-CONTEXTE-AGENT.md`
§6. La réciproque vaut ici : un plan de génération d'image qui conclurait au succès dès le premier
essai devrait être relu deux fois.
