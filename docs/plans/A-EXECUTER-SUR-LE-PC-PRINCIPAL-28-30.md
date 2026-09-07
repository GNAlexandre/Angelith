# À exécuter sur le PC PRINCIPAL — fermer les lots 28, 29 et 30

> **Écrit le 2026-09-03**, dépôt en **2.24.0**, à la fin du lot 30.
>
> **À qui ce fichier s'adresse.** À Alexandre, devant le PC principal (ComfyUI + RX 7900 XT),
> et à la session Claude Code qu'il ouvrira là-bas. Il rassemble **tout ce que les trois lots
> n'ont pas pu vérifier**, dans l'ordre où il faut le faire, avec ce qu'il faut relever et où
> l'écrire.
>
> **Comment démarrer la session, là-bas :**
>
> ```
> Lis docs/plans/00-CONTEXTE-AGENT.md puis
> docs/plans/A-EXECUTER-SUR-LE-PC-PRINCIPAL-28-30.md.
> Exécute le bloc A, publie ses relevés, et arrête-toi pour que je les relise.
> ```
>
> ⚠ **Aucune ligne de ce document ne demande d'écrire du code.** Ce sont des commandes à lancer
> et des chiffres à recopier. Si une session propose d'écrire du code pour « faire marcher »
> l'un de ces points, c'est que le point a échoué — et l'échec est le résultat qu'il faut
> publier, pas contourner.

---

## 0. Pourquoi ce document existe

Trois lots de suite ont tourné sur le **PC secondaire**, qui n'a ni ComfyUI, ni carte, ni les
poids, ni la bible. Le bilan honnête, lot par lot :

| Lot | Version | Ce que son document de mesure conclut | Ce qui bloque |
|---|---|---|---|
| 28 — voir ce que le projet envoie | 2.22.0 | **3 critères sur 9 non tenus** | la machine, et rien d'autre |
| 29 — le juge et le corpus | 2.23.0 | 2 tenus, 2 à moitié, **5 non tenus** | la machine, **les poids du juge**, et **la bible** |
| 30 — les canaux qui manquent | 2.24.0 | 4 tenus, 2 à moitié, **3 non tenus** | la machine, **et le lot 29** |

⚠ **Les colonnes ne s'additionnent pas en un seul chiffre**, et c'est délibéré : les trois
documents ne comptent pas les « à moitié » de la même façon. Chacun reprend ses critères un par
un ; c'est là qu'il faut lire, pas dans un total.

⚠ **Une distinction que le README de la série a fini par apprendre, et qui commande cet
ordre** : « se lance sur le PC principal » est une condition **trop grossière**. Trois
ressources différentes manquaient, et elles ne se débloquent pas au même prix :

| Ressource | Ce qu'elle coûte | Ce qu'elle ouvre |
|---|---|---|
| **les poids du juge** (`dinov2-base.onnx`, 346 Mo) | 20 min, **sur n'importe quelle machine** | l'étalonnage du juge — CPU suffit |
| **la bible** (`sources/<Projet>/bible.yaml`) | une demi-journée d'Alexandre | le corpus, donc tout le lot 29 |
| **ComfyUI + la carte** | la machine | tout ce qui génère |

**Le bloc A ci-dessous ne demande que la machine et cinq minutes.** Faites-le en premier :
il ferme des cases sans rien attendre de personne.

---

## Bloc A — la machine seule, ~20 minutes, aucune génération

> Ferme : **lot 28 critères 1 et 3**, **lot 30 critère 7**, et lève une réserve du lot 30.

### A.1 — Ce que le serveur expose réellement (lot 28, critère 1)

```powershell
python tools/comfy.py --sonde
```

**À relever et à recopier** dans `docs/procedures/comfyui.md` **§0**, en remplaçant le tableau
daté du 2026-08-29 :

- la version de ComfyUI, la variante d'installation, le dossier d'installation et de modèles ;
- `extra_model_paths.yaml` s'il existe ;
- **les nœuds tiers, avec le module qui les fournit** — et, à la main, la **licence** de chacun
  vérifiée à sa source primaire : elle ne se déduit de rien ;
- la VRAM totale, libre et réservée.

⚠ **Le §0 bis de la fiche dit déjà que ce tableau n'a pas été remesuré.** Quand vous le
remplacez, **datez-le du jour** et retirez l'avertissement — c'est la règle des affirmations
d'état (`00-CONTEXTE-AGENT.md` §5 bis).

### A.2 — Les quatre graphes contre le VRAI `/object_info` (lot 28, critère 3)

```powershell
python tools/comfy.py --valider
```

**Attendu** :

| Graphe | Attendu |
|---|---|
| `qwen-image-2512.api.json` | ✓ rien à signaler, **plus** la réserve `copie_non_marquee` (normale, elle est sur tous) |
| `qwen-image-2512-lightning.api.json` | idem |
| `qwen-image-edit-2511.api.json` | idem |
| `qwen-image-edit-2511-controle.api.json` | ⚑ **GRAPHE CANDIDAT** en tête, puis des **réserves** (pas des refus) sur le nœud et le poids absents |

⚠ **Le code de sortie doit être 0.** S'il vaut 1, lisez lequel des quatre a un **refus** : c'est
un vrai défaut, sur la vraie machine, et c'est exactement ce que le lot 28 cherchait.

⚠ **Point de vérification du lot 30** : le graphe candidat ne doit **pas** faire échouer la
commande. Si c'est le cas, la rétrogradation `_retrograder` ne fonctionne pas comme prévu.

**À noter** : les vérifications 2 et 3 (« nœuds exposés », « fichiers et listes ») n'avaient
**jamais** été exercées contre un vrai serveur — seulement contre un `/object_info` factice.
C'est leur première.

### A.3 — Le diagnostic, avec un vrai serveur (lot 28, critère 5 — déjà tenu)

```powershell
python run_illustration.py --check
```

**Attendu** : la validation du graphe apparaît dans le diagnostic, **avec le serveur
joignable** — ce qu'aucune session n'a encore vu. Le critère 5 est marqué tenu, mais il l'était
« trivialement » : `--check` ne décharge jamais rien, donc « refuse avant tout déchargement de
LLM » ne prouvait pas grand-chose. Ce que cette ligne vérifie vraiment, c'est que les
vérifications 2 et 3 s'affichent **passées** au lieu de « NON FAIT ».

### A.4 — `/free`, vingt appels (lot 30, critère 7) — ⚠ la seule mesure indépendante de tout

```powershell
python run_illustration.py --liberer-vram --repetitions 20
```

⚠ **Lancez-la après une génération**, sinon il n'y a rien à libérer et le test ne teste rien.
Elle **sonde le serveur entre chaque appel** : le mode d'échec est que ComfyUI **meurt**, pas
qu'il rende une erreur.

**Trois issues, et chacune a sa suite :**

| Ce que dit le relevé | Ce qu'il faut faire |
|---|---|
| `0 panne(s) sur 20 appels — dénominateur atteint` | ⚠ **le chiffre soutient d'armer.** Passer `illustration.vram.decharger_image` à `true` **est alors une décision d'Alexandre**, à écrire à la main, avec le chiffre et la version de ComfyUI en commentaire |
| `N panne(s) sur 20` avec N ≥ 1 | **garder désarmé**, et publier le taux avec sa version. Le geste manuel reste documenté |
| `ARRÊT au k-ième appel` | relancer ComfyUI et **reprendre** : les dénominateurs s'additionnent. Trois sessions de 7 valent un dénominateur de 21 |

**À écrire** : le couple `(pannes / appels, version de ComfyUI)` dans un nouveau
`docs/mesures/canaux-<date>.md`, ou en addendum daté de celui du 2026-09-03.

---

## Bloc B — les poids du juge, ~20 minutes, **n'importe quelle machine**

> Ferme : **lot 29 critère 2**, pour le corpus actuel.

⚠ **Ce bloc n'a jamais eu besoin du PC principal**, et personne ne l'avait vu. DINOv2 tourne
sur CPU sous `onnxruntime`, qui est déjà installé. Ce qui manquait, ce sont les **poids** — que
le dépôt ne télécharge pas, par choix : la licence se vérifie à la source primaire.

```powershell
# 1. déposer dinov2-base.onnx sous illustration_models/
# 2. renseigner illustration.identite.encodeur.fichier et son sha256 dans config.yaml
#    (⚠ vérifier la licence des poids à la SOURCE PRIMAIRE, et écrire la date)
python tools/banc_identite.py "roman S" --etalonnage --markdown
```

**À relever** : le recouvrement, à publier **à côté des 68/100** du lot 25 — pas à sa place.
C'est le point de comparaison « avant » de tout le lot 29.

---

## Bloc C — la bible, une demi-journée d'Alexandre

> Ferme : **lot 29 critères 1 et 2**, et débloque **tout le reste de la série**.

⚠ **C'est le verrou.** Sans corpus, le juge ne se réétalonne pas ; sans juge, aucune
amélioration d'identité ne se **constate** ; sans constat, aucun canal ne se livre. Les lots 29
et 30 s'arrêtent tous les deux ici.

```powershell
python tools/bible.py "roman S" --corpus              # où en est le corpus, sans rien relire
python tools/bible.py "roman S" --revue --role identite
```

**La cible, écrite par le plan 29** : **8 personnages**, dont **4 à ≥ 3 références**, et
**aucune couverture**. L'état de départ, tel que `README-COMFYUI-28-30.md` §1 le relève : les
**3 premières** références validées sont des **couvertures**, dont 2 le même dessin, et **un
seul** personnage porte plus d'une référence — là où les axes qui génèrent en demandaient 8
et 10.

```powershell
# puis, le corpus corrigé :
python tools/banc_identite.py "roman S" --etalonnage --markdown
```

**La question à trancher, et c'était l'hypothèse 0.1 du plan 29** : *le juge ne sépare
peut-être pas parce que le corpus est mauvais, pas parce que la métrique est mauvaise.* Si le
recouvrement s'améliore nettement sur le corpus corrigé, la métrique n'était pas en cause — et
il ne faut **pas** changer de métrique. Le plan 29 L29.3 reste fermé tant que ce chiffre
n'existe pas.

---

## Bloc D — la génération : le lot 28 finit, le lot 29 se juge

> Ferme : **lot 28 critères 4 et 6**, **lot 29 critères 3, 4, 5, 6 et 7**.
> Coût : ~5 h de carte, plus une demi-journée d'œil.

### D.1 — Le graphe rejoué à la main (lot 28, critère 4)

```powershell
python tools/comfy.py --graphe build/<Projet>/illustrations/requete.yaml
```

Puis : **glisser le `.api.json` produit dans ComfyUI**, lancer, et **comparer l'image obtenue au
PNG du run**. C'est le seul critère du lot 28 qui demande un geste à la souris.

**Attendu** : la même image, à l'octet près si la pile est déterministe (elle l'était le
2026-08-30). Une image différente signifierait que le graphe archivé n'est pas celui qui est
parti — et ce serait un défaut grave, puisque c'est ce fichier qui rend la mesure rejouable.

### D.2 — Le graphe et le journal archivés (lot 28, critère 6)

```powershell
python run_illustration.py "<Projet>" --phase image
python tools/comfy.py --journal
```

**À vérifier** : `<image>.png.graphe.json` existe à côté de l'image, et le sidecar de provenance
porte `journal_serveur` avec les **trois lignes qui décident** — `loaded completely` /
`loaded partially`, `lowvram patches: N`, `Prompt executed in …`.

⚠ **La route `/internal/logs/raw` n'a jamais été appelée contre un vrai ComfyUI.** C'est sa
première aussi.

### D.3 — Le coût, publié AVANT de lancer (lot 29, critère 7)

```powershell
python tools/banc_identite.py "roman S" --devis --decors neutre,trame,aucun
```

### D.4 — Le balayage, axe décor compris (lot 29, critère 5)

```powershell
python tools/banc_identite.py "roman S" Vol.1 --personnage "<nom>" --balayage --decors neutre,trame,aucun --markdown
```

**Ce que ça tranche** : la part d'aplats, **avec et sans** « fond neutre ». Le gabarit retenu
sera celui que la mesure désigne — et **pas** avant : le défaut reste `neutre` tant qu'aucun
chiffre ne désigne un remplaçant.

### D.5 — Le protocole en aveugle (lot 29, critères 3 et 4) — ⚠ **le livrable central**

```powershell
python tools/juge_humain.py "roman S" --paires 20 --seuil 14
python tools/juge_humain.py "roman S" --rapport --markdown
```

⚠ **Le seuil se fixe ICI, à la création, pas au rapport.** Il n'existe pas d'option `--seuil` à
la lecture, et c'est délibéré : un seuil qu'on peut passer après avoir vu les résultats ne
mesure rien.

⚠ **C'est une demi-journée d'œil humain, ni parallélisable ni délégable.** C'est elle qui
dimensionne le lot, pas le GPU.

**Ce que ça tranche, enfin** : le verdict d'identité. La voie A tient, ou elle ne tient pas.
Toute colonne « ressemblance » du dépôt est marquée **non opposable** jusqu'à ce chiffre.

---

## Bloc E — le canal de contrôle (lot 30)

> Ferme : **lot 30 critères 1, 2, 3 et 5**.
> ⚠ **Ne commencez pas ce bloc avant que D.5 ait donné un verdict.** Un canal ne se juge que
> sur son apport, et l'apport ne se constate qu'avec un juge qui sépare. C'est la raison d'être
> de l'ordre de la série, et le lot 30 s'est arrêté précisément là.

### E.1 — Le poids, sa licence et son empreinte (critère 2)

```powershell
# 1. télécharger qwen_image_canny_diffsynth_controlnet.safetensors depuis
#    https://huggingface.co/Comfy-Org/Qwen-Image-DiffSynth-ControlNets
#    (amont : DiffSynth-Studio/Qwen-Image-Blockwise-ControlNet-Canny)
# 2. ⚠ REVÉRIFIER la licence à la source, le JOUR de l'installation — Apache-2.0 au 2026-09-03,
#    mais « une page bouge »
# 3. le déposer dans ComfyUI/models/model_patches/
# 4. RELEVER SON SHA-256 : c'est la moitié manquante du critère 2
Get-FileHash <chemin> -Algorithm SHA256
# 5. REDÉMARRER ComfyUI — il ne relit ses dossiers qu'au démarrage
```

**À écrire** : le SHA-256 et la date de vérification **dans le bloc `_candidat` du graphe**,
à la place du texte « NON RELEVE ».

### E.2 — Le graphe, validé avant toute génération

```powershell
python tools/comfy.py --valider illustration/workflows/qwen-image-edit-2511-controle.api.json
```

**Attendu après E.1** : plus aucune réserve `noeud_absent` ni `modele_absent`. Il reste la
mention ⚑ CANDIDAT (elle est dans le fichier, elle ne disparaît qu'en la retirant) et la
réserve `canal_exige`, qui est normale.

### E.3 — ⚠ **UNE seule image**, pour lever la réserve de compatibilité

**C'est le point le plus incertain de tout le lot 30, et il faut le traiter en premier.** Le
`MODEL_PATCH` est publié pour **Qwen-Image** (texte-vers-image) ; le graphe candidat l'empile
sur **Qwen-Image-Edit-2511 quantifié en Q4_1**. Rien n'établit que les deux soient compatibles.

```powershell
#   config.yaml : illustration.comfyui.workflow ->
#       "illustration/workflows/qwen-image-edit-2511-controle.api.json"
#   requete.yaml : canaux.image_de_controle: "<un trait, une silhouette, un croquis>"
python run_illustration.py "<Projet>" --phase image
python tools/comfy.py --journal
```

| Ce qui se passe | Ce que ça veut dire |
|---|---|
| ComfyUI refuse le patch (erreur de forme de tenseur, dimension) | **le patch ne s'applique pas au transformeur d'édition.** Repli : `qwen-image-2512-lightning.api.json` — qui perd les références, donc l'identité, donc l'essentiel de l'intérêt. À publier comme résultat négatif |
| une image sort | passer à E.4 |
| ⚠ **`lowvram patches: N` apparaît dans le journal** | 🛑 **ARRÊT. Le canal ne se livre pas**, même s'il améliore l'image. C'est le critère 3 du plan, écrit d'avance : le transformeur a été rogné, et le lot 24 a chiffré ce que ça coûte — **facteur 9,6** sur le pas de débruitage |

**À relever dans tous les cas** : `loaded completely` ou `loaded partially`, le `lowvram
patches` s'il apparaît, le pic de VRAM, et les **secondes par image contre les 233,7 s** de
l'édition à une référence.

### E.4 — L'apport, sur le même banc et le même juge que les références (critère 5)

```powershell
python tools/banc_identite.py "<Projet>" <Tome> --personnage "<nom>" --balayage --controle <trait.png> --markdown
```

**Les quatre grandeurs sont publiées côte à côte** : ressemblance (opposable seulement après
D.5), nouveauté, style, et **temps par image**.

⚠ **Le seuil de refus est déjà écrit** : « un canal qui gagne 0,01 de style pour +120 s par
image est un canal qu'on documente et qu'on ne livre pas. »

### E.5 — Et remettre le graphe par défaut

```powershell
#   config.yaml : illustration.comfyui.workflow -> "illustration/workflows/qwen-image-2512-lightning.api.json"
```

⚠ **Sauf si E.3 et E.4 concluent que le canal se livre** — auquel cas c'est une décision à
écrire, avec ses chiffres, et non un réglage à laisser traîner.

---

## Bloc F — les deux points optionnels, si l'envie est là

### F.1 — `PreviewImage` : la copie qui ne traîne plus (lot 30, §6.2)

Le lot 30 a écrit, **sans le mesurer**, que remplacer `SaveImage` par `PreviewImage` dans un
graphe ferait atterrir la copie de ComfyUI dans `temp/` — vidée à son redémarrage — sans
changer une ligne du client, parce que celui-ci transmet à `/view` le `type` que l'historique
lui donne. **C'est une lecture du code, pas un relevé.**

Pour en faire un relevé : éditer une copie d'un graphe, y mettre `PreviewImage`, générer, et
vérifier que l'image arrive et que le fichier est bien dans `temp/`. Cinq minutes.

### F.2 — Les nœuds EliGen, si le canal de contrôle échoue

Si E.3 conclut que le patch ne s'applique pas, le canal des **entités + masques** redevient
candidat. ⚠ Il coûte alors un **nœud tiers** (`ComfyUI-QwenImageWanBridge`, ou
`ComfyUI_Qwen-Image`) : relever son dépôt, sa licence et **sa date de dernier commit** avant
toute chose — « un canal qui dépend d'un nœud abandonné est une dette ». Et il n'aura toujours
pas de source de masques : le lot 29 a mesuré que le rectangle proposé ne fait pas ce qu'on
espérait.

---

## Ce qu'il faudra publier à la fin

Un document par lot fermé, dans `docs/mesures/`, qui **reprend les critères un par un** — la
règle du §9.6 de `00-CONTEXTE-AGENT.md`. Le plus simple est un **addendum daté** à chacun des
trois documents existants, plutôt qu'une réécriture :

| Lot | Document à compléter | Ce qu'il faut y ajouter |
|---|---|---|
| 28 | [`../mesures/comfy-visible-2026-09-02.md`](../mesures/comfy-visible-2026-09-02.md) | les critères 1, 3, 4 et 6, avec les sorties réelles |
| 29 | [`../mesures/identite-2026-09-03.md`](../mesures/identite-2026-09-03.md) | les critères 1 à 7, et **le verdict d'identité** |
| 30 | [`../mesures/canaux-2026-09-03.md`](../mesures/canaux-2026-09-03.md) | les critères 1, 2, 3, 5 et 7 |

⚠ **Ne réécrivez pas les documents datés.** Ils décrivent l'état de leur jour, c'est leur
fonction, et les corriger effacerait l'histoire de la mesure — `00-CONTEXTE-AGENT.md` §5 bis
l'écrit explicitement. Un addendum daté, ou un nouveau document qui cite l'ancien.

⚠ **Un tableau qui ne confirme jamais que le plan n'est pas une mesure.** Si un chiffre
contredit ce que ces trois lots ont supposé, **écrivez-le** : c'est le résultat le plus utile
que cette série puisse produire.
