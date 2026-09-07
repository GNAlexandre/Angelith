# Les workflows ComfyUI — le connecteur, et ce qu'il a coûté de le mesurer

Quatre graphes au **format API**, dérivés du template officiel `image_qwen_Image_2512` de
`comfyui-workflow-templates` 0.11.50, avec `UNETLoader` remplacé par `UnetLoaderGGUF`.

| Fichier | Pas | Guidage | LoRA | Ce qu'il sert à faire |
|---|---:|---:|---|---|
| `qwen-image-2512.api.json` | 50 | 4,0 | — | le réglage de **référence** du template officiel |
| `qwen-image-2512-lightning.api.json` | 4 | **1,0** | Lightning 4 steps | l'usage courant, texte-vers-image |
| `qwen-image-edit-2511.api.json` | 4 | **1,0** | Edit Lightning 4 steps | **la voie A du `PLAN-25`** : le seul graphe ARMÉ qui porte `%reference_1%` |
| `qwen-image-edit-2511-controle.api.json` | 4 | **1,0** | Edit Lightning 4 steps | ⚑ **CANDIDAT, jamais exécuté** — le canal « image de contrôle » du `PLAN-30` |

⚠ **Les trois premiers ont tourné ; le quatrième non, et il le dit lui-même.** Un graphe qui
porte un bloc racine `_candidat` est un graphe de **mesure**, pas du chemin nominal — voir
« Le graphe candidat » plus bas.

⚠ **Le guidage n'est pas un réglage libre.** La LoRA Lightning est distillée sans guidage libre
de classifieur : à `cfg: 4` elle produit des images brûlées. Ce ne sont pas deux réglages du
même moteur, ce sont **deux moteurs**, et `illustration.image.pas` / `guidage` doivent suivre le
workflow choisi.

---

## Le `PLAN-24` disait de ne pas livrer de graphe. Pourquoi il y en a un maintenant

Le plan écrivait : « en écrire un ici, sans avoir pu l'exécuter, aurait produit un fichier
**plausible et faux** ». C'était juste, et c'est pourquoi le lot 24 n'en livrait aucun.

Ces deux-là ont **tourné**, le 2026-08-29, sur une RX 7900 XT sous ROCm 7.14, ComfyUI 0.34.2.
Les chiffres ci-dessous sont relevés, pas estimés. La raison d'être de l'abstention a disparu ;
l'abstention avec.

⚠ **Ils restent liés à une pile précise** : ComfyUI 0.34.2, `ComfyUI-GGUF` (city96, Apache-2.0),
et les quatre fichiers de modèle nommés dans les nœuds. Sur une autre pile, ce sont des
**points de départ**, pas des garanties — c'est exactement le statut qu'un graphe ComfyUI peut
avoir.

## Ce que la mesure a changé dans le graphe, et pourquoi

**`CLIPLoader.device: "cpu"` n'est pas un repli pour petite carte : c'est le réglage le plus
rapide sur 20 Go**, et c'est contre-intuitif au point qu'il faut le chiffrer.

L'encodeur de texte `Qwen2.5-VL-7B` pèse **7 910 Mio** et le transformeur Q4_1 **12 284 Mio** —
**20 194 Mio** à eux deux, pour **20 464 Mio** de VRAM. Les laisser tous les deux sur la carte
ne tient donc qu'à 270 Mio près, et ComfyUI s'en sort en **rognant le transformeur** :

```
Unloaded partially: 1921.69 MB freed, 9064.05 MB remains loaded, lowvram patches: 707
```

Le transformeur passe alors en mode « lowvram » et se diffuse depuis la RAM à chaque pas.
Mesuré sur la même image, même graine, même prompt :

| Encodeur | Pas de débruitage | Image complète | Pic VRAM |
|---|---:|---:|---:|
| sur GPU (`device: default`) | **64,3 s/pas** | ~260 s | 13 799 Mio |
| **sur CPU (`device: cpu`)** | **6,7 s/pas** | **103,7 s** (médiane, 4 images) | 14 417 Mio |

**Facteur 9,6 sur l'échantillonnage.** L'encodage sur CPU coûte ~76 s par image, mais il rend
la carte entière au transformeur, et c'est lui qui domine.

⚠ **Le pic de VRAM est plus HAUT avec l'encodeur sur CPU** (14 417 contre 13 799 Mio), et ce
n'est pas une contradiction : c'est le signe que le transformeur tient enfin *en entier* sur la
carte. Un pic plus bas décrivait un modèle qu'on avait dû rogner.

## Pourquoi 50 pas coûtent 6,1 fois plus, et pas 12,5

Le rapport de pas est de 12,5 (50 contre 4), mais le rapport de temps mesuré est de **6,1**
(629,8 s contre 103,7 s, médianes sur 4 images chacune).
Deux effets se composent, et aucun n'est un détail :

- **le guidage double le travail par pas.** À `cfg > 1`, ComfyUI fait *deux* passes avant par
  pas — conditionnée et non conditionnée — pour le guidage libre de classifieur. Mesuré :
  **6,7 s/pas à `cfg 1,0`** contre **9,7–10,05 s/pas à `cfg 4,0`** ;
- **un coût fixe d'environ 76 s par image** — encodage du texte sur CPU, chargement du VAE,
  décodage — qui pèse énormément sur une image de 4 pas (27 s d'échantillonnage) et presque
  rien sur une de 50 pas (~500 s).

D'où : `103,7 s ≈ 76 + 27` et `629,8 s ≈ 76 + 500`.

⚠ **Et 50 pas n'achètent pas le registre graphique** — c'est mesuré, pas jugé à l'œil. L'écart
moyen au tome passe de 0,200 à 0,1525 (−24 %), mais la **densité de trait ne bouge pas** :
0,0522 à 4 pas, 0,0536 à 50 pas, contre **0,2664** pour le tome. Le régime de couleur reste
faux dans les deux cas. Le style n'est pas un problème de calcul — c'est le `PLAN-25`.

## Lot 25 — l'édition, et une prémisse du lot 24 renversée

`qwen-image-edit-2511.api.json` est le premier graphe du dépôt qui porte `%reference_1%`. Il
réutilise l'encodeur de texte et le VAE déjà installés ; seuls le transformeur (12,84 Go) et sa
LoRA (0,85 Go) s'ajoutent.

### ⚠ `CLIPLoader.device` est `"default"` ici, et `"cpu"` dans les deux autres. Ce n'est pas une incohérence

C'est une **prémisse héritée que la mesure a renversée**, et elle mérite d'être écrite en
toutes lettres parce qu'elle contredit un chiffre publié quatre heures plus tôt.

- **en texte-vers-image**, l'encodeur ne fait que du **texte**. Le mettre sur CPU coûte ~76 s et
  rend la carte entière au transformeur : facteur **9,6** sur le pas de débruitage (lot 24) ;
- **en édition**, le **même** encodeur fait tourner la **tour de vision** de `Qwen2.5-VL` sur
  chaque image de référence — en fp8, donc émulé sur CPU.

Mesuré le 2026-08-29, même image, même graine, une référence à 1024 px :

| `CLIPLoader.device` | Image complète |
|---|---:|
| `default` (GPU) | **233,7 s** |
| `cpu` | le nœud `TextEncodeQwenImageEditPlus` tournait **encore après 307 s**, et n'a jamais été vu terminer |

Le journal du serveur nomme le coupable sans ambiguïté :

```
execution_interrupted  node_id: 20  node_type: TextEncodeQwenImageEditPlus
executed: ['4', '21', '10']
```

— le chargement de l'encodeur, l'encodage négatif et le chargement de l'image étaient faits ;
c'est l'encodage **image + texte** qui n'avançait plus.

⚠ **La règle générale n'est donc ni « CPU » ni « GPU », c'est : mettez l'encodeur là où est le
travail.** Un graphe qui ne lui donne que du texte gagne à le sortir de la carte ; un graphe qui
lui donne des images doit l'y laisser.

### Ce que coûte l'édition, comparée au texte-vers-image

| Chemin | Secondes / image (1328 × 1328, 4 pas) |
|---|---:|
| texte-vers-image (lot 24, médiane sur 4) | **103,7 s** |
| **édition, 1 référence** (lot 25) | **233,7 s** |

Le facteur est de **2,25**, et il s'explique : la référence est encodée par la tour de vision
**et** par le VAE, et ses jetons s'ajoutent à la séquence d'attention du transformeur à chaque
pas.

### Le latent part d'une toile vide, pas de la référence

`EmptySD3LatentImage` et non `VAEEncode` : à `denoise: 1.0`, le contenu initial du latent ne
compte pas, seule sa **forme** compte. Partir de la référence lierait la dimension de sortie à
celle de la page source ; on veut la choisir.

### Les trois `LoadImage`, et pourquoi il y en a trois

`TextEncodeQwenImageEditPlus` n'expose que `image1`, `image2` et `image3`. Le graphe les câble
toutes les trois, et **le client élague** les nœuds dont le marqueur n'a pas été substitué : une
requête à une seule référence part avec un seul `LoadImage`. C'est ce qui rend le balayage
« 1, 2 ou 3 références » possible avec **un seul fichier** plutôt que trois qui divergeraient au
premier réglage changé.

### Les références sont TÉLÉVERSÉES, pas passées par chemin

Mesuré : `LoadImage` refuse un chemin absolu — `Invalid image file: C:\…\media\….jpeg`. ComfyUI
ne résout ses images que sous son propre dossier `input/`. Le client les lui donne donc par
`POST /upload/image`, dans un sous-dossier `angelith/`, sous un nom qui porte l'empreinte du
contenu — de sorte que deux runs de même requête envoient le même graphe.

⚠ **Une copie de l'extrait reste donc chez ComfyUI, en entrée cette fois.** C'est la même
réserve qu'en sortie : la frontière d'écriture d'Angelith couvre **ses** écritures, pas celles
d'un programme tiers que l'utilisateur a installé. Ces copies sont des extraits de l'œuvre,
elles restent locales, et les supprimer ne casse rien.

## Les marqueurs, et les canaux qu'ils déclarent

| Marqueur | Type | Canal |
|---|---|---|
| `%prompt%`, `%prompt_negatif%` | texte | `prompt`, `prompt_negatif` |
| `%graine%`, `%largeur%`, `%hauteur%`, `%pas%`, `%guidage%` | scalaire | — (aucun moteur ne les refuse) |
| `%reference_1%`… | chemin | `references` |
| `%entite_1%` / `%masque_1%`… | texte / chemin | `entites` |
| `%image_controle%` | chemin | `image_controle` |

Un marqueur **seul** dans un champ prend le **type** de sa valeur (`"%graine%"` devient l'entier
42, pas la chaîne « 42 » — ComfyUI refuserait la chaîne) ; un marqueur **dans une phrase** est
interpolé en texte.

⚠ **Les deux workflows texte-vers-image ne portent aucun marqueur de référence, de masque ou
d'image de contrôle** ; celui d'édition porte les trois marqueurs de référence et **pas** ceux
de masque ni d'image de contrôle. ⚠ **Le graphe CANDIDAT du lot 30 porte, lui, les références
ET `%image_controle%`** — et il est le seul, sur les quatre, à **exiger** un canal. Aucun ne
porte `%masque_1%` : le canal `entites` reste refusé partout.

Le moteur **refuse donc explicitement** les canaux absents, avec leur motif, avant la première
seconde de GPU — et non en silence. Vérifié le 2026-08-29 sur la requête réelle de `roman S`,
qui portait 10 références :

```
canal « references » refusé par le moteur « comfyui » : le workflow
qwen-image-2512-lightning.api.json ne porte aucun marqueur %reference_1%
```

Le conditionnement sur images de référence — donc l'identité du personnage — est le sujet du
`PLAN-25`, pas de celui-ci.

## Écrire le vôtre

Exportez depuis ComfyUI : ⚙ → « Enable Dev mode Options », puis **« Save (API Format) »**. Un
export normal décrit l'écran, pas le graphe, et le client le dit.

Puis remplacez les valeurs par les marqueurs voulus. Le client accepte les clés de commentaire
à la racine — `_commentaire` ici — et les retire avant l'envoi : **ComfyUI itère sur toutes les
clés racine** et tombe sur une clé qui n'est pas un nœud.

## Ce que ces fichiers ne disent pas

- **rien sur la ressemblance d'un personnage.** Le graphe d'édition la *conditionne* ; savoir
  si elle *tient* est une mesure, et son verdict est dans
  `docs/mesures/identite-2026-08-29.md` — où il est nuancé : le juge automatique ne sépare pas
  assez pour trancher, et le protocole en aveugle n'a pas été exécuté ;
- **le registre graphique dépend du graphe.** Mesuré le 2026-08-29 : les deux graphes
  texte-vers-image produisent des images **photoréalistes**, très loin du trait d'un light
  novel ; le graphe d'**édition**, conditionné par les références du tome, produit du trait en
  noir et blanc. Les chiffres sont dans `docs/mesures/identite-2026-08-29.md` §4 ;
- **rien sur les autres piles** : ni `stable-diffusion.cpp`, ni `diffusers`, ni une autre carte.

⚠ **Une copie NON MARQUÉE reste chez ComfyUI.** Le nœud `SaveImage` écrit dans le dossier de
sortie de ComfyUI ; Angelith récupère l'image, la marque et l'écrit dans
`build/<Projet>/<Tome>/illustrations/`. La copie de ComfyUI, elle, ne porte ni bloc `tEXt` ni
sidecar. La frontière d'écriture d'Angelith couvre **ses** écritures, pas celles d'un programme
tiers que l'utilisateur a lancé lui-même.

> ⚠ **MISE À JOUR 2026-09-03, lot 30 — la fin de ce paragraphe était FAUSSE.** Elle conseillait
> de « remplacer `SaveImage` par `SaveImageWebsocket` ». **Ce client ne sait pas lire ce
> nœud** : il récupère l'image par `GET /history/<id>` puis `GET /view`, et
> `SaveImageWebsocket` ne publie rien dans l'historique — il pousse les octets sur une
> connexion WebSocket que ce client n'ouvre pas. Un graphe qui le porte s'exécuterait,
> occuperait la carte plusieurs minutes, puis échouerait sur « n'a produit aucune image ».
> Le validateur le **refuse** désormais avant le GPU (`sortie_websocket`).
>
> **Le bon conseil, et il ne coûte rien au client : `PreviewImage`.** ComfyUI l'écrit dans
> son dossier `temp/`, qu'il **vide à chaque redémarrage**, et il le publie dans l'historique
> avec `type: temp` — que ce client transmet déjà tel quel à `/view` (`comfyui.py`, l'appel
> `get_bytes("/view", …)` lit `premiere.get("type", "output")`). Aucune ligne à changer.
>
> ⚠ **Aucun graphe du dépôt ne l'utilise encore, et ce n'est pas un oubli** : cette phrase
> décrit une **lecture du code**, pas un relevé. Le `PLAN-30` critère 6 demandait de trancher
> `SaveImageWebsocket` — c'est fait, il est refusé, avec son motif. Adopter `PreviewImage`
> dans les graphes livrés change où atterrit une copie que certains utilisateurs veulent
> garder : c'est un changement de comportement, il se mesure d'abord.

## Le graphe candidat — `qwen-image-edit-2511-controle.api.json`, lot 30

⚑ **Il n'a jamais été exécuté, au 2026-09-03**, et le poids qu'il nomme n'est installé sur
aucune machine du dépôt. Il est livré comme **instrument de mesure** : sans lui, l'apport du
canal « image de contrôle » ne peut pas être mesuré, et sans cette mesure le canal ne peut pas
être livré. Le `PLAN-30` appelle cela lever le blocage « dans le bon sens ».

| Ce qu'il ajoute au graphe d'édition | Nœud |
|---|---|
| charge le patch de contrôle | `ModelPatchLoader` (intégré à ComfyUI) |
| reçoit l'image de contrôle | `LoadImage` sur `%image_controle%` |
| applique le patch **au modèle** | `QwenImageDiffsynthControlnet` (intégré) |

Trois choses à savoir avant de le désigner dans `illustration.comfyui.workflow` :

1. **il faut déposer un poids**, `qwen_image_canny_diffsynth_controlnet.safetensors`, sous
   `ComfyUI/models/model_patches/`, depuis
   `huggingface.co/Comfy-Org/Qwen-Image-DiffSynth-ControlNets` — **Apache-2.0, vérifiée à la
   source le 2026-09-03**. Son empreinte SHA-256 n'est **pas** relevée : le fichier n'a pas
   été téléchargé, et le critère 2 du plan exige l'empreinte du fichier *récupéré*, le jour de
   l'installation ;
2. **il EXIGE le canal.** Ce graphe place son nœud de contrôle **en série sur le chemin du
   modèle** : sans `canaux.image_de_controle` dans `requete.yaml`, l'élagage emporte le nœud
   et le `KSampler` perd son modèle. Le graphe le déclare (`_candidat.exige`) et le moteur
   refuse **avant le GPU**, avec le nom du champ à remplir. C'est le premier graphe du dépôt
   qui ne dégrade pas, et `moteur.CanalExige` existe pour lui ;
3. **la réserve qu'il faut lire** : le patch est publié pour **Qwen-Image** (texte-vers-image)
   et ce graphe l'empile sur **Qwen-Image-Edit-2511** quantifié en Q4_1. Rien, au 2026-09-03,
   n'établit que les deux sont compatibles. C'est la première chose à constater. En cas
   d'échec, le repli est `qwen-image-2512-lightning.api.json` — qui perd les références, donc
   l'identité, donc l'intérêt.

**Pourquoi canny et pas depth**, alors que le plan parle de *pose* : une carte de profondeur
demande un estimateur de profondeur, c'est-à-dire un modèle de plus que le dépôt n'a pas et
refuserait (interdit n° 4). Une carte de contours se dérive d'un trait, et une planche de manga
**est** du trait. Le dépôt ne fabrique **aucune** image de contrôle : elle est fournie par
l'utilisateur.

**Pourquoi ce canal et pas les entités + masques (EliGen)** : ce choix se fait sur la **dette**
et non sur l'apport, qui n'est mesuré ni pour l'un ni pour l'autre. `ModelPatchLoader` et
`QwenImageDiffsynthControlnet` sont **intégrés** à ComfyUI ; EliGen exige un nœud **tiers**
(`ComfyUI-QwenImageWanBridge`, ou `ComfyUI_Qwen-Image`) qui n'est installé sur aucune machine
du dépôt. À apport inconnu des deux côtés, on instrumente celui qui ne crée aucune dette.
