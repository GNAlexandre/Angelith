# Plans 28 à 30 — la brique d'illustration face à son instance ComfyUI

Établis le **2026-08-31**, dépôt en **2.18.0**, après les lots 23 à 26.

**Commencez par [`00-CONTEXTE-AGENT.md`](00-CONTEXTE-AGENT.md), puis
[`README-ILLUSTRATION-23-27.md`](README-ILLUSTRATION-23-27.md)** — la décision d'usage, la frontière
« l'IA ne dessine jamais *sur* l'œuvre », le run en deux phases et la porte humaine y sont posés et
ne sont pas rouverts ici.

⚠ **Nouveau fait de terrain, et il commande l'exécution de ces trois plans.** ComfyUI et la
RX 7900 XT sont sur le **PC principal** ; la copie de travail lue par une session peut être celle du
PC secondaire, qui n'a **ni serveur ni carte**. C'est exactement ce qui a produit le lot 24 avec
« trois des quatre mesures que le plan demandait n'ont pas pu être faites ». **Tout plan de cette
série qui contient une mesure se lance sur le principal**, et l'étape 0 de chacun commence par le
dire.

---

## 1. Où en est la brique, au 2026-08-31

| Version | Lot | Ce qu'elle a livré |
|---|---|---|
| 2.14.0 | 23 | la bible visuelle : signature de style du tome, genre résolu, références validées |
| 2.15.0 | 24 | la quatrième brique, la frontière **testée**, le marquage sans interrupteur, le client ComfyUI — **jamais exécuté** |
| 2.16.0 | 24 étape 0.3 + VRAM | le connecteur **mesuré sur la 7900XT** : six défauts que seul le réel montrait ; `/free` livré **désarmé** |
| 2.17.0 | 25 | la voie A produit **le bon registre** (−39 % d'écart au tome), et **le juge ne sépare pas** |
| 2.18.0 | 26 | le prompt vient de l'œuvre ; ce n'est pas sa **forme** qui décide, c'est le **choix des images** |

**Trois acquis solides**, chiffrés et reproductibles : le conditionnement par référence bat le calcul
(−39 % d'écart de style à nombre de pas identique, contre −24 % pour 12,5 fois plus de pas) ; les
images sont enfin **en noir et blanc comme le tome**, par deux leviers indépendants ; la
reproductibilité est **octet pour octet** sur cette pile.

**Quatre trous, tous nommés par les documents de mesure eux-mêmes :**

| Trou | Le chiffre | Conséquence |
|---|---|---|
| **le juge ne sépare pas** | 68 séparations sur 100 à un seuil de 80 | toute colonne « ressemblance » du dépôt est **non opposable**, et le protocole humain en aveugle n'a **jamais** été exécuté |
| **le corpus de références** | les 3 premières références validées sont des **couvertures**, dont 2 le même dessin ; **un seul** personnage porte plus d'une référence | les axes qui génèrent ont tourné sur **1 personnage** et **2 à 3 images**, là où le plan demandait 8 et 10 |
| **le registre, en partie** | densité de trait **0,1188** contre **0,2664** pour le tome ; part d'aplats **0,6300** contre 0,3669 — elle a **empiré** | « nettement amélioré, pas réglé », et une moyenne qui progresse cache une régression |
| **aucun canal structuré** | nœuds EliGen **absents** du serveur ; `ModelPatchLoader` expose une liste **vide** | ni position, ni forme, ni pose — alors qu'il reste **8,4 à 9,1 Go** libres après une génération |

Et **deux plans de la série précédente ne sont pas lancés** : le `PLAN-27` (l'atelier dans
l'interface) et le `PLAN-17` (le traducteur manga qui cesse de travailler à l'aveugle).

## 2. Les trois plans

| Plan | Objet | Nature attendue | Jours |
|---|---|---|---|
| [28](PLAN-28-VOIR-CE-QUE-LE-PROJET-ENVOIE.md) ✅ **livré en 2.22.0** | **Voir** : la sonde, le validateur de graphe, le graphe archivé, un `--check` qui refuse avant le GPU | MINEUR | 8 |
| [29](PLAN-29-LE-JUGE-ET-LE-CORPUS.md) ⚠ **outillé en 2.23.0, 7 critères sur 9 NON TENUS** | **Juger** : le corpus de références qui manque, le protocole humain jamais exécuté, le juge qui ne sépare pas | MINEUR | 12 |
| [30](PLAN-30-LES-CANAUX-QUI-MANQUENT.md) ⚠ **outillé en 2.24.0, AUCUN CANAL LIVRÉ, 3 critères sur 9 non tenus** | **Contrôler** : entités et masques, image de contrôle, et la copie non marquée qui traîne | MINEUR | 10 |

**Total : 30 jours**, plus les 10 du `PLAN-27` qui reste dû.

> ⚠ **Le 28 est livré (2.22.0, 2026-09-02), avec trois de ses neuf critères NON TENUS** — et
> les trois pour la même raison, celle que ce README annonçait : **la session a tourné sur le PC
> secondaire.** Ce qui manque ne demande pas de code, seulement dix minutes sur le principal ;
> les six commandes sont au §9 de [`../mesures/comfy-visible-2026-09-02.md`](../mesures/comfy-visible-2026-09-02.md).
>
> **Ce que le 29 et le 30 héritent quand même** : `tools/comfy.py`, `illustration/sonde.py` et
> `illustration/validation.py` sont livrés et testés contre un `/object_info` factice. Le
> validateur sur lequel « les deux autres plans s'appuient » existe.

> ⚠ **Le 29 est outillé (2.23.0, 2026-09-03), avec SEPT de ses neuf critères NON TENUS** — et
> pour une raison plus large que celle du 28 : la session a de nouveau tourné sur le PC
> secondaire, où manquent **trois** ressources et non une. Ni `bible.yaml` (0 fichier sur
> 17 projets), ni les poids de l'encodeur du juge, ni ComfyUI et la carte.
>
> ⚠ **Et le plan avait une étape exécutable SANS GPU que personne n'avait vue** : l'étape 0.1
> — « réétalonnez le juge inchangé » — ne demande qu'un CPU, DINOv2 tournant sous
> `onnxruntime`. Elle a été bloquée par l'absence des **poids**, pas par celle de la carte.
> « Se lance sur le principal » est donc une condition trop grossière, et les plans suivants
> gagneraient à distinguer *ce qui demande la carte* de *ce qui demande le corpus*.
>
> **Ce que le 30 hérite quand même** : le protocole en aveugle est **outillé et testé**
> (`illustration/aveugle.py`, `tools/juge_humain.py`), le corpus se **compte**
> (`tools/bible.py --corpus`), le coût GPU se **publie avant de lancer**
> (`--devis`), et deux défauts silencieux sont corrigés — le champ de recadrage écrit sous un
> nom et lu sous un autre depuis la 2.14.0, et `banc_identite --balayage` qui levait un
> `AttributeError` depuis la 2.18.0. Les sept commandes qui ferment les sept critères sont au
> §10 de [`../mesures/identite-2026-09-03.md`](../mesures/identite-2026-09-03.md).
>
> ⚠ **Le verrou de la série reste fermé** : sans juge qui sépare, aucune amélioration
> d'identité ne peut être constatée. Le `PLAN-30` en dépend, et le `PLAN-27` — déjà livré en
> 2.21.0 — affiche donc toujours un verdict de ressemblance non opposable.

> ⚠ **Le 30 est outillé (2.24.0, 2026-09-03), et il ne livre AUCUN CANAL** — troisième session
> d'affilée sur le PC secondaire, mais cette fois ce n'est pas la machine qui décide : le
> critère 1 du plan exigeait de choisir un canal **sur son apport mesuré**, et le 29 n'a pas
> livré cette mesure. Même lancé sur le principal, ce lot n'aurait pas pu tenir ce critère.
> **La conséquence a été tirée plutôt que contournée.**
>
> ⚠ **Le choix du canal instrumenté s'est donc fait sur la DETTE, pas sur l'apport**, et c'est
> écrit comme tel : `ModelPatchLoader` et `QwenImageDiffsynthControlnet` sont **intégrés** à
> ComfyUI, EliGen exige un nœud **tiers**. À apport inconnu des deux côtés, on instrumente
> celui qui ne crée aucune dette.
>
> **Ce que le lot livre quand même** : un graphe **candidat** qui se déclare comme tel
> (`illustration/workflows/qwen-image-edit-2511-controle.api.json`) et que le validateur
> connaît sans passer en rouge ; `CanalExige`, la réciproque du refus, pour le premier graphe
> du dépôt qui **ne dégrade pas** ; une sixième vérification qui tranche la copie non marquée
> (`SaveImageWebsocket` **refusé**, avec un motif mécanique — ce client ne sait pas le lire) ;
> le protocole compté de `/free` (`--liberer-vram --repetitions 20`) ; l'axe `canal` du banc,
> fermé par défaut ; et **un défaut silencieux corrigé** — `%image_controle%` n'était pas un
> marqueur élagable, ce qu'aucun graphe livré ne pouvait révéler. Les cinq étapes qui ferment
> ce qui reste sont au §11 de
> [`../mesures/canaux-2026-09-03.md`](../mesures/canaux-2026-09-03.md).
>
> ⚠ **Une seule d'entre elles est indépendante du 29** : le relevé de `/free`, cinq minutes.
> Tout le reste attend que le verrou du 29 s'ouvre.

## 2 bis. ⚠ Ce qui reste dû, en un seul fichier — 2026-09-03

Les trois lots sont livrés, et **chacun laisse des critères ouverts** — trois pour le 28, sept
pour le 29, cinq pour le 30, en comptant les « à moitié » (chaque document de mesure les reprend
un par un). Aucun ne demande d'écrire du code : ils demandent une session sur le PC principal,
les poids du juge, et une demi-journée d'Alexandre sur la bible.

**Tout est rassemblé, dans l'ordre, avec ce qu'il faut relever et où l'écrire :**
[`A-EXECUTER-SUR-LE-PC-PRINCIPAL-28-30.md`](A-EXECUTER-SUR-LE-PC-PRINCIPAL-28-30.md).

⚠ **Son bloc A ne coûte que vingt minutes et n'attend rien de personne** — la sonde, les quatre
graphes contre le vrai serveur, et le relevé de `/free` sur vingt appels. Faites-le en premier :
il ferme quatre cases à lui seul.

## 3. Ordre, et il n'est pas négociable

1. **28 d'abord**, parce que c'est le plan qui répond à « la construction se fait à travers le projet
   sans que j'aie de vision sur ce dernier ». Il ne change pas une image : il rend visible le graphe
   envoyé, valide un workflow **avant** le GPU, et dit ce que le serveur expose réellement. Les deux
   autres plans s'appuient sur son validateur.
2. **29 ensuite**, et c'est le verrou de toute la série. Sans juge qui sépare, aucune amélioration
   d'identité ne peut être **constatée** — on ne saurait pas si un changement a aidé. ⚠ Son étape 0
   doit tester une hypothèse avant toute chose : *le juge ne sépare peut-être pas parce que le
   corpus est mauvais*, pas parce que la métrique est mauvaise. Trois couvertures dont deux
   identiques ne sont pas un corpus d'identité.
3. **30 en dernier**, parce qu'un canal ne se juge que sur son apport mesuré, et que la mesure
   dépend du 29.
4. **Le `PLAN-27` peut se glisser après le 29** — pas avant : un atelier qui affiche un verdict de
   ressemblance non opposable donnerait à croire que la question est réglée.

## 4. L'écart à corriger dès le 28

`illustration/comfyui.py` l. 34 affirme encore, dans sa docstring :

> « Ce client **n'a jamais tourné contre un vrai serveur ComfyUI**. »

C'était vrai en 2.15.0. Depuis, la 2.16.0 l'a mesuré sur 25 générations avec **0 échec
d'exécution**, et la 2.18.0 a fait tourner un run complet de bout en bout. La phrase est donc
**fausse dans le code source**, alors qu'elle reste juste dans
`docs/mesures/socle-generatif-2026-08-29.md` — qui est un document **daté**, et qui a le droit de
décrire l'état de son jour.

C'est la leçon générale, et le `PLAN-28` L28.4 la traite : **une affirmation d'état dans le code
porte sa date, ou elle finit par mentir.** Le dépôt a déjà cette règle pour les chiffres
(« un chiffre sans dénominateur n'est pas une mesure ») ; elle vaut aussi pour les états.
