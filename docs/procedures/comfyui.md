# ComfyUI — apprendre à s'en servir, et y brancher Angelith

> **Cette fiche s'adresse à quelqu'un qui n'a jamais construit un graphe ComfyUI** et qui doit
> pourtant comprendre celui que la brique d'illustration lui envoie. Elle est écrite **avec les
> chiffres relevés sur ta machine** les 2026-08-29 et 30, pas avec ceux d'un tutoriel : c'est ce
> qui la rend utilisable et ce qui la rend périssable.
>
> ⚠ **Tout ce qui suit se lance sur le PC PRINCIPAL.** ComfyUI n'est pas installé sur le PC
> secondaire, et la carte non plus. Une session Claude Code qui doit toucher à ComfyUI doit donc
> tourner sur le principal, sinon elle mesurera le vide — ce qui est exactement ce qui s'est
> passé au lot 24 (`docs/mesures/socle-generatif-2026-08-29.md` : « trois des quatre mesures que
> le plan demandait n'ont pas pu être faites »).

---

## 0. Ce que tu as déjà, et qu'il ne faut pas reconstruire

> **Relevé le 2026-09-03, sur le PC PRINCIPAL**, par `python tools/comfy.py --sonde` et par une
> lecture directe de `GET /system_stats`. Il **remplace** le tableau du 2026-08-29
> (`docs/mesures/connecteur-qwen-2026-08-29.md`), qui reste vrai pour son jour. Le détail de la
> session est dans `docs/mesures/comfy-visible-2026-09-02.md` §10 (addendum du 2026-09-03).

| | |
|---|---|
| Carte | RX 7900 XT, **20 464 Mio** de VRAM (`21 458 059 264` octets), ROCm 7.14, Windows 11 26200 — **inchangé** depuis le 2026-08-29 |
| Serveur | ComfyUI **0.34.2** (commit `169fcf35`), `torch 2.12.0+rocm7.14.0`, Python 3.13.12, **907 nœuds exposés** — les quatre **inchangés** depuis le 2026-08-29 |
| Variante — **tranchée** | `Comfy Desktop 1.0.46` **pilotant** un environnement **standalone `win-amd`** (bundle `v0.29.0-env1`). Ce n'était pas « l'un ou l'autre » : c'est les deux à la fois, ce qui est exactement pourquoi la question ne se tranchait pas |
| Dossier d'installation | `%LOCALAPPDATA%\Comfy-Desktop\ComfyUI-Installs\ComfyUI\ComfyUI\` |
| Dossier de modèles | ⚠ `%LOCALAPPDATA%\Comfy-Desktop\**ComfyUI-Shared**\models\` — **pas** `models/` sous l'installation, qui ne contient que ses fichiers `put_*_files_here` |
| Chemins supplémentaires | **pas** de `extra_model_paths.yaml` à la racine. Desktop passe le même contenu en ligne de commande : `--extra-model-paths-config "%APPDATA%\Comfy Desktop\instance-model-paths\inst-1788013776283.yaml"` |
| Nœud tiers | **un seul** : `ComfyUI-GGUF` (city96) — 6 nœuds, commit `6ea2651` du 2026-01-12, **Apache-2.0 vérifiée à la source primaire le 2026-09-03** (`github.com/city96/ComfyUI-GGUF`, fichier `LICENSE` du dépôt et de la copie installée) ; paquet `gguf 0.19.0` |
| ⚠ Faux tiers | `websocket_image_save` (1 nœud). La sonde le compte comme tiers parce qu'il vit sous `custom_nodes/` — mais il est **versionné par ComfyUI lui-même** (`git ls-files` sur la v0.34.2 le rend). Sa licence est donc celle de ComfyUI, **GPL-3.0**, et il n'y a **rien à installer** |
| Modèles | **six fichiers**, tailles relevées sur le disque le 2026-09-03 : `qwen-image-2512-Q4_1.gguf` (`12 843 678 240` o) · `qwen-image-edit-2511-Q4_1.gguf` (`12 843 678 304` o) · `qwen_2.5_vl_7b_fp8_scaled.safetensors` (`9 384 670 680` o) · `qwen_image_vae.safetensors` (`253 806 246` o) · les deux LoRA Lightning (`849 608 296` o chacune) |
| Graphes | **quatre** au 2026-09-03, dans `illustration/workflows/` : trois qui ont tourné, dont deux portent `%reference_1%`, plus **un CANDIDAT** (`…-controle.api.json`) qui n'a jamais tourné et dont le poids n'est installé nulle part — voir §7 bis |

⚠ **L'encodeur de texte et le VAE sont PARTAGÉS par tous les graphes du dépôt** ; le transformeur et la LoRA,
non — le graphe d'édition a les siens. C'est ce qui fait que passer du texte-vers-image à l'édition
coûte deux fichiers de plus, pas six.

⚠ **Un chiffre du tableau précédent ne se reconstitue pas.** Il annonçait l'encodeur de texte à
« 7 910 Mio » ; le fichier sur le disque en fait **8 950** (`9 384 670 680` octets). Aucun fichier
de cette machine ne pèse 7 910 Mio, et le chiffre de 2026-08-29 ne portait pas son dénominateur —
on ne peut donc ni le confirmer ni le corriger, seulement le remplacer par une mesure qui dit d'où
elle vient. C'est le cas d'école de la règle des chiffres (`00-CONTEXTE-AGENT.md` §5).

### 0 bis. La commande qui relève tout cela — lot 28, 2026-09-02

```powershell
python tools/comfy.py --sonde
```

Elle rend la version, la variante d'installation, le dossier d'installation et de modèles,
`extra_model_paths.yaml` s'il existe, **les nœuds tiers avec le module qui les fournit**, la VRAM
totale, libre et réservée, et pour chacun des graphes du dépôt : ses nœuds existent-ils, et
ses fichiers de modèle sont-ils dans les listes que le serveur expose.

⚠ **MISE À JOUR 2026-09-03 : l'avertissement « ce tableau n'a pas été remesuré » est LEVÉ.** Le §0
ci-dessus est le relevé du 2026-09-03 sur le principal. Ce qui suit le remplace : **trois écarts
entre ce que la sonde affirme et ce que cette machine est**, trouvés en la lançant pour la première
fois contre un vrai serveur. Aucun n'a été corrigé dans cette session — le document qui les
instruit est `docs/mesures/comfy-visible-2026-09-02.md` §10.

| Ce que la sonde affiche ici | Ce qui est vrai | D'où vient l'écart |
|---|---|---|
| « Modèles : `…\ComfyUI\models` » | les modèles sont sous `…\ComfyUI-Shared\models` | la sonde déduit `models/` du dossier de `main.py`. Sous Desktop, c'est le **mauvais** dossier, et il est vide |
| « `extra_model_paths.yaml` : absent — les modèles sont lus sous l'installation » | un fichier de chemins **existe**, hors de l'installation, passé en argument | la sonde ne cherche le fichier qu'à la racine de l'installation. `/system_stats` rend pourtant `argv`, où `--extra-model-paths-config` est écrit en toutes lettres |
| « installée (Desktop ou venv) » | Desktop, sans ambiguïté | `/system_stats` rend `deploy_environment: "local-desktop2-standalone"`, que la sonde ne lit pas. Le §0 bis disait que la distinction « ne se déduit de rien » : **elle se déduit**, d'un champ qui existe |

⚠ **Les deux premières lignes se tiennent l'une l'autre** : la sonde dit « les modèles sont lus
sous l'installation » **parce qu'**elle n'a pas vu le fichier de chemins. Un lecteur qui suivrait
son indication déposerait un poids dans un dossier que ce serveur ne lit pas — et c'est précisément
le piège que le §2 de cette fiche prétend éviter. La **licence** de chaque nœud tiers, elle, ne se
déduit toujours de rien : elle se vérifie à la source primaire et s'écrit ici, à la main.

---

## 1. Le modèle mental, en cinq idées

Tout le reste en découle. Si ces cinq idées sont claires, un graphe inconnu se lit en deux minutes.

1. **Un nœud est une fonction.** Il a des entrées à gauche, des réglages au milieu, des sorties à
   droite. `UnetLoaderGGUF` rend un `MODEL` ; `CLIPTextEncode` prend un `CLIP` et une chaîne, rend
   un `CONDITIONING`. Rien de plus.
2. **Un lien est typé, et le type est la moitié de la doc.** Tu ne peux pas brancher un `MODEL` sur
   une entrée `CLIP` : l'interface refuse. Quand tu cherches quel nœud mettre, regarde **le type
   qu'il te manque**, pas le nom que tu imagines.
3. **La file est le seul moment où quelque chose s'exécute.** Tu construis à froid, tu cliques
   « Run » (ou `Ctrl+Entrée`), ComfyUI met la requête **en file** et l'exécute. Rien ne tourne
   pendant que tu édites.
4. **L'exécution est paresseuse et cachée.** ComfyUI remonte les dépendances depuis les nœuds de
   sortie et **ne recalcule que ce qui a changé**. Changer la graine ne recharge pas les 12,84 Go du
   modèle : seul l'échantillonnage repart. C'est pour cela que la **première** image d'une session
   coûte 172 s et les suivantes 103,7 s (médiane sur 4).
5. **Il y a deux JSON, et ils ne servent pas à la même chose.** Le format « workflow » décrit
   **l'écran** (positions, couleurs, nœuds désactivés) ; le format **API** décrit **le graphe**
   (nœuds, entrées, liens). Angelith ne lit que le second, et le dit quand on lui donne le premier.

---

## 2. Où vont les fichiers de modèle

C'est la question qui bloque tout le monde au début, et la réponse est bêtement mécanique : **la
liste déroulante d'un nœud est le contenu d'un dossier.** Si ton fichier n'apparaît pas, il n'est pas
dans le bon dossier, ou le serveur n'a pas été relancé.

| Ce que tu télécharges | Où il va | Quel nœud le lit |
|---|---|---|
| transformeur `.safetensors` | `models/diffusion_models/` (ex-`unet/`) | `UNETLoader` |
| transformeur **`.gguf`** | `models/unet/` ou `models/diffusion_models/` selon la version du nœud | **`UnetLoaderGGUF`** (nœud tiers) |
| encodeur de texte `Qwen2.5-VL-7B` | `models/text_encoders/` (ex-`clip/`) | `CLIPLoader`, type `qwen_image` |
| VAE `qwen_image_vae` | `models/vae/` | `VAELoader` |
| LoRA Lightning | `models/loras/` | `LoraLoaderModelOnly` |
| nœud tiers (`ComfyUI-GGUF`…) | `custom_nodes/<nom>/` | — |

Trois réflexes qui évitent des heures :

- **Relance le serveur après avoir ajouté un fichier de modèle ou un nœud.** Les listes sont lues
  au démarrage. Le bouton « Refresh » de l'interface rafraîchit les listes de modèles, pas les
  nœuds.
- **Ne renomme pas un fichier après l'avoir mis dans un graphe.** Le graphe stocke le **nom**, pas
  un identifiant. C'est aussi ce qui casse un `.api.json` versionné dans le dépôt.
- **Un modèle sur un autre disque** se déclare dans `extra_model_paths.yaml` (à la racine de
  ComfyUI, à copier depuis `extra_model_paths.yaml.example`) plutôt qu'en copiant 12 Go deux fois.

**Vérifier sans deviner, depuis le dépôt :** `GET /object_info` rend la description de tous les
nœuds **et le contenu des listes déroulantes**. `tools/banc_prompt.py` le fait déjà (l. 267) — c'est
là que le lot 26 a lu « 907 nœuds » et « `ModelPatchLoader` expose une liste **vide** ».

---

## 3. Le premier graphe : texte → image, nœud par nœud

**Commence par le template, puis reconstruis-le à la main.** `Workflow → Browse Templates →
image_qwen_Image_2512` te donne un graphe qui marche ; le refaire de zéro une fois est ce qui te
donne la vision que tu cherches. Les graphes du dépôt viennent de ce template
(`comfyui-workflow-templates 0.11.50`), avec `UNETLoader` remplacé par `UnetLoaderGGUF`.

La chaîne minimale, dans l'ordre où on la construit :

```
UnetLoaderGGUF ─MODEL─► LoraLoaderModelOnly ─MODEL─► ModelSamplingAuraFlow ─MODEL─┐
                                                                                  ├─► KSampler ─LATENT─► VAEDecode ─► SaveImage
CLIPLoader ─CLIP─► CLIPTextEncode (positif) ─────────────────────────────COND─────┤                          ▲
            └────► CLIPTextEncode (négatif) ─────────────────────────────COND─────┤                          │
                                        EmptySD3LatentImage ────────────LATENT────┘             VAELoader ───┘
```

⚠ **`ModelSamplingAuraFlow` (`shift: 3.1`) n'est pas décoratif** et c'est le nœud qu'on oublie en
reconstruisant à la main : il règle l'échelle de bruit attendue par cette famille de modèles. Sans
lui, mêmes poids et même graine donnent autre chose.

Ce que chaque nœud demande, et la seule valeur qui compte :

| Nœud | Réglage qui décide | Valeur mesurée sur ta pile |
|---|---|---|
| `UnetLoaderGGUF` | le fichier | `Qwen-Image-2512` **Q4_1** — 12 284 Mio en VRAM, chargé **en entier** (`full load: True`) |
| `CLIPLoader` | `type: qwen_image` et **`device`** | **`cpu` en texte-vers-image** — voir l'encadré ci-dessous |
| `LoraLoaderModelOnly` | la LoRA Lightning, `strength_model: 1.0` | change le **régime** du graphe, pas un réglage |
| `ModelSamplingAuraFlow` | `shift: 3.1` | valeur du template officiel ; ne la touche pas sans mesurer |
| `EmptySD3LatentImage` | 1328 × 1328 | le carré natif de la famille Qwen-Image |
| `KSampler` | `steps`, `cfg`, `seed`, `denoise` | **4 pas / cfg 1,0** avec Lightning ; **50 pas / cfg 4,0** sans. `sampler_name: euler`, `scheduler: simple`, `denoise: 1.0` dans tous |
| `VAEDecode` + `VAELoader` | le VAE | 241 Mio, chargé en dernier |
| `SaveImage` | le préfixe | ⚠ écrit une copie **non marquée** — voir §9 |

> ### ⚠ L'encadré à retenir : `CLIPLoader.device`
>
> **Mets l'encodeur là où est le travail.**
>
> - **texte → image** : l'encodeur ne traite que du texte. Le laisser sur le GPU force ComfyUI à
>   rogner le transformeur (`Unloaded partially: 1921.69 MB freed, … lowvram patches: 707`), qui se
>   diffuse alors depuis la RAM à chaque pas. Mesuré : **64,3 s/pas** sur GPU contre **6,7 s/pas**
>   avec `device: cpu`, soit un **facteur 9,6**. L'encodage sur CPU coûte ~76 s par image et les
>   rend au centuple.
> - **édition (avec références)** : le **même** encodeur fait tourner la **tour de vision** de
>   `Qwen2.5-VL` sur chaque image. Sur CPU, en fp8 émulé, le nœud
>   `TextEncodeQwenImageEditPlus` **tournait encore après 307 s** sans jamais finir. Sur GPU :
>   **233,7 s** pour l'image complète.
>
> Et un contre-sens de lecture à connaître : **le pic de VRAM est plus HAUT dans la bonne
> configuration** (14 417 contre 13 799 Mio). Un pic plus bas décrivait un modèle qu'on avait dû
> rogner.

⚠ **`cfg` n'est pas un curseur de qualité.** La LoRA Lightning est distillée **sans** guidage libre
de classifieur : à `cfg 4` elle produit des images brûlées. Et à `cfg > 1`, ComfyUI fait **deux**
passes avant par pas — mesuré : 6,7 s/pas à `cfg 1,0` contre 9,7-10,05 s/pas à `cfg 4,0`. Le
graphe Lightning et le graphe de référence ne sont pas deux réglages du même moteur, ce sont **deux
moteurs**.

---

## 4. Le second graphe : ajouter des images de référence

C'est celui qui t'intéresse — c'est lui qui fait « le bon personnage ». Cinq différences avec le
précédent, relevées dans `qwen-image-edit-2511.api.json` :

0. **ce n'est pas le même transformeur, ni la même LoRA** : `qwen-image-edit-2511-Q4_1.gguf` et
   `Qwen-Image-Edit-2511-Lightning-4steps`. L'encodeur de texte et le VAE, eux, sont les mêmes — donc
   deux fichiers à télécharger, pas six.
1. **`CLIPTextEncode` devient `TextEncodeQwenImageEditPlus`**, et il y en a **deux** : un pour le
   prompt, un pour le négatif. Il prend le `CLIP`, le texte, **et** `image1`, `image2`, `image3` —
   pas plus de trois, c'est le nœud qui le décide.
2. **Trois `LoadImage` sont câblés**, même quand tu n'as qu'une référence. Angelith **élague** les
   nœuds dont le marqueur n'a pas été substitué : c'est ce qui permet de balayer « 1, 2 ou 3
   références » avec **un seul fichier** de graphe.
3. **`CLIPLoader.device` repasse à `default`** (voir l'encadré du §3).
4. Le latent part d'`EmptySD3LatentImage`, **pas** de `VAEEncode` : à `denoise: 1.0` le contenu
   initial ne compte pas, seule la **forme** compte, et on veut choisir la dimension de sortie
   plutôt que d'hériter de celle de la page source.

⚠ **`LoadImage` refuse un chemin absolu** — `Invalid image file: C:\…\media\….jpeg`. ComfyUI ne
résout ses images que sous son propre dossier `input/`. Le connecteur les téléverse donc par
`POST /upload/image` dans un sous-dossier `angelith/`, sous un nom qui porte l'empreinte du contenu.
Quand tu construis à la main, **glisse l'image dans le nœud** `LoadImage` : elle est copiée dans
`input/`.

Le prix mesuré de l'édition : **233,7 s** contre **103,7 s** en texte-vers-image, soit un facteur
**2,25** — la référence est encodée par la tour de vision **et** par le VAE, et ses jetons
s'ajoutent à la séquence d'attention à chaque pas.

Et le résultat qui justifie tout : à nombre de pas identique, le conditionnement par référence
réduit l'écart de style au tome de **0,2000 à 0,1224 (−39 %)**, là où passer de 4 à 50 pas
n'achetait que −24 % pour 12,5 fois plus de calcul.

---

## 5. Lire ce qui se passe : la console, puis trois routes HTTP

**La console du serveur est la vraie interface de diagnostic.** Quatre lignes à savoir lire :

| Ligne | Ce qu'elle dit |
|---|---|
| `Requested to load …` / `loaded completely` | le modèle tient sur la carte |
| `loaded partially` / `lowvram patches: N` | ⚠ il a été **rogné** — attends-toi au facteur 9,6 |
| `execution_interrupted node_id: … node_type: …` | quel nœud était en cours quand tu as coupé |
| `Prompt executed in … seconds` | le temps réel, celui qu'on publie |

Et les routes que tu peux appeler à la main (navigateur ou `curl`) :

| Route | Ce qu'elle rend |
|---|---|
| `GET /system_stats` | version, backend, VRAM totale et libre |
| `GET /object_info` | tous les nœuds **et le contenu des listes de modèles** |
| `GET /queue`, `GET /history/<id>` | ce qui attend, ce qui est fini |
| `GET /internal/logs/raw` | **la console, en JSON** — les quatre lignes ci-dessus sans quitter le terminal |
| `POST /free` `{"unload_models":true,"free_memory":true}` | rend la carte : **12 083 Mio → ~470 Mio** |

⚠ **Depuis le lot 28, tu n'as plus à lire la console pour savoir si le transformeur a été rogné.**
Les trois lignes qui décident — `loaded completely` / `loaded partially`, `lowvram patches: N`,
`Prompt executed in …` — sont **archivées à côté de chaque image**, dans son sidecar de
provenance, et `python tools/comfy.py --journal` les relit. C'est la différence entre une trace et
un souvenir : la console s'efface au redémarrage du serveur, le sidecar non.

⚠ **Ce n'est pas une corrélation par `prompt_id`.** ComfyUI n'étiquette pas ses lignes de journal
par requête : Angelith prend la **queue** du journal au moment où il récupère l'image. Sur un
serveur qui ne sert que ce run — le cas nominal, la carte étant bloquée pendant la génération —
c'est la bonne fenêtre ; sur un serveur partagé, ce sont les dernières lignes, et le champ
`correlation` du sidecar le dit.

⚠ **`/free` fait segfauter ComfyUI environ une fois sur sept** — relevé le 2026-08-29 : sur sept
appels, un a produit une violation d'accès `0xC0000005` dans son propre
`comfy/model_management.py:model_unload`. Le plantage est chez ComfyUI, pas dans Angelith. C'est
pour cette raison exacte que `illustration.vram.decharger_image` est livré **désarmé** : les images
sont écrites et marquées **avant** cet appel, donc rien n'est perdu, mais il faut relancer le
serveur.

⚠ **Et « une fois sur sept » n'est pas une mesure, c'est une impression** — sept n'est pas un
dénominateur. Depuis le lot 30 (2026-09-03), le geste manuel est **outillé et compté** :

```powershell
python run_illustration.py --liberer-vram                     # rendre la carte, une fois
python run_illustration.py --liberer-vram --repetitions 20    # le RELEVÉ que le PLAN-30 demande
```

La seconde forme **sonde le serveur entre deux appels**, parce que le mode d'échec n'est pas
« l'appel rend une erreur » mais « ComfyUI meurt » : une boucle naïve compterait dix-neuf succès
imaginaires après le premier plantage. Elle s'arrête au premier serveur mort, dit à quel rang, et
rappelle que les dénominateurs s'additionnent d'une session à l'autre.

⚠ **Elle n'arme rien et ne relance rien.** Le chiffre se lit, la décision s'écrit à la main dans
`config.yaml` — et le `PLAN-30` interdit explicitement de relancer ComfyUI à sa place : « Angelith
ne pilote pas le cycle de vie d'un programme que l'utilisateur a installé ».

⚠ **Au 2026-09-03, ce relevé n'a PAS été fait** : la session du lot 30 tournait sur le PC
secondaire. Le chiffre en vigueur reste 1 sur 7, du 2026-08-29, avec sa version de ComfyUI.

---

## 6. Brancher Angelith sur ton graphe

Le dépôt ne fabrique **aucun** graphe : il substitue des marqueurs dans le tien. C'est un choix
écrit — « un graphe ComfyUI est propre à un modèle, à une version de nœuds et à une machine ; en
écrire un ici, sans avoir pu l'exécuter, aurait produit un fichier plausible et faux ».

**La procédure, dans l'ordre :**

1. Construis et **fais tourner** ton graphe dans ComfyUI. Un graphe qui n'a pas produit une image
   n'est pas un graphe.
2. ⚙ → **« Enable Dev mode Options »**, puis **« Save (API Format) »**. Un export normal décrit
   l'écran, pas le graphe.
3. Remplace les valeurs par les marqueurs voulus :

| Marqueur | Type | Canal déclaré |
|---|---|---|
| `%prompt%`, `%prompt_negatif%` | texte | `prompt`, `prompt_negatif` |
| `%graine%`, `%largeur%`, `%hauteur%`, `%pas%`, `%guidage%` | scalaire | — (aucun moteur ne les refuse) |
| `%reference_1%`, `%reference_2%`, `%reference_3%` | chemin | `references` |
| `%entite_1%` / `%masque_1%`… | texte / chemin | `entites` |
| `%image_controle%` | chemin | `image_controle` |

   Un marqueur **seul** dans un champ prend le **type** de sa valeur (`"%graine%"` devient l'entier
   42, pas la chaîne « 42 », que ComfyUI refuserait) ; un marqueur **dans une phrase** est interpolé
   en texte. Une clé de racine commençant par `_` (`_commentaire`) est acceptée et retirée avant
   l'envoi — sans ça, ComfyUI itère sur toutes les clés racine et tombe sur une clé qui n'est pas un
   nœud.

4. **C'est le graphe qui déclare ce que le moteur sait faire.** `CANAUX_SUPPORTES` est **lu dans le
   graphe** : un canal dont le marqueur n'apparaît nulle part est **refusé avec un motif nommé**,
   avant la première seconde de GPU — jamais honoré à moitié, jamais jeté en silence :

   ```
   canal « references » refusé par le moteur « comfyui » : le workflow
   qwen-image-2512-lightning.api.json ne porte aucun marqueur %reference_1%
   ```

5. Renseigne `config.yaml` — et **fais correspondre les pas et le guidage au graphe** :

```yaml
illustration:
  actif: true
  moteur: "comfyui"          # défaut "factice" : un carré uni qui vérifie la chaîne, pas l'image
  image:
    pas: 4                   # 4 + guidage 1.0 avec la LoRA Lightning
    guidage: 1.0             # 50 + 4.0 pour qwen-image-2512.api.json
  comfyui:
    base_url: "http://127.0.0.1:8188"
    workflow: "illustration/workflows/qwen-image-edit-2511.api.json"
    timeout: 600             # la 1re génération charge 12,84 Go depuis le disque
```

6. **Valide le graphe avant d'y mettre une seconde de GPU** — lot 28 :

```powershell
python tools/comfy.py --valider illustration/workflows/qwen-image-edit-2511.api.json
python tools/comfy.py --valider          # sans argument : les quatre graphes du dépôt + le tien
```

   Cinq contrôles, aucun watt : le fichier est-il au format API ; chaque `class_type` existe-t-il
   sur **ton** serveur ; chaque fichier de modèle nommé est-il dans la liste que le nœud expose ;
   quels canaux ce graphe déclare ; et **les pas et le guidage sont-ils compatibles avec sa LoRA**.
   Chaque refus porte sa correction, et le code de sortie vaut 1 — donc il se scripte.

   ⚠ **La cinquième est la seule dont l'échec ne produit aucun message côté ComfyUI.** `cfg 4` avec
   une LoRA Lightning s'exécute très bien et sort une image brûlée. C'est la première ligne du §10
   ci-dessous, et rien ne la signalait avant ce lot.

   ⚠ **Serveur éteint : les contrôles 2 et 3 sont NON FAITS, pas passés**, et l'outil l'écrit avec
   ces mots. Les contrôles 1, 4 et 5 marchent hors ligne, donc sur le PC secondaire aussi.

7. Lance, dans cet ordre :

```powershell
python run_illustration.py --check                              # l'environnement, avant tout GPU
python run_illustration.py "<Projet>" <Tome> --phase prompt      # phase 1 : le LLM remplit requete.yaml
#   relis et corrige build/<Projet>/<Tome>/illustrations/requete.yaml, puis valide: true
python tools/comfy.py --graphe build/<Projet>/illustrations/requete.yaml   # VOIR ce qui partira
python run_illustration.py "<Projet>" <Tome> --phase image       # phase 2 : bascule VRAM + génération
python run_illustration.py --rejouer <image>.provenance.json     # rejeu exact d'une requête passée
```

⚠ **`--check` fait tourner la validation ci-dessus** depuis la 2.22.0, et refuse **avant** le
déchargement du LLM : un nœud absent, un modèle renommé ou un guidage incompatible ne coûtent plus
le chargement de 12,84 Go de poids pour être découverts.

⚠ **`--graphe` est ce qui rend la vision.** Il écrit dans `graphes/`, à côté du `requete.yaml`, le
JSON **exactement tel qu'il partirait** — marqueurs substitués, nœuds élagués, images de référence
sous le nom que ComfyUI leur donnera. Il **n'envoie rien** et **ne téléverse rien** : le nom d'une
référence est calculé depuis l'empreinte de son contenu. Glisse ce fichier dans ComfyUI : il
recharge le graphe exact, graine comprise, et tu rejoues à la main ce que le projet a fait tourner.

⚠ **Les deux phases ne coexistent jamais en VRAM.** `illustration.vram.decharger_llm: true`
décharge `yume-27b` d'Ollama avant que ComfyUI ne touche à la carte ; le rechargement appartient à
l'appelant. Et la phase 2 **refuse** de démarrer sur `valide: false`.

---

## 7. Ajouter un nœud tiers, et les deux canaux qui manquent

Un nœud tiers s'installe soit par **ComfyUI-Manager** (interface, recherche, un clic), soit par
`git clone` dans `custom_nodes/` suivi d'un **redémarrage** et de `pip install -r requirements.txt`
dans l'environnement du serveur. C'est ainsi que `ComfyUI-GGUF` est arrivé chez toi.

Deux canaux ont été inventoriés à la source le 2026-08-30 et **ne sont pas installés** :

| Canal | Ce qui manque | Licence | Ce qu'il apporterait |
|---|---|---|---|
| **entités + masques** (`EliGen`) | **aucun nœud ne l'expose** sur ton serveur | `Qwen-Image-EliGen-V2`, 0,2 Md, Apache-2.0 vérifiée | la **position et la forme** : cadrage voulu, place du personnage, fond non uni |
| **image de contrôle** (pose) | `ModelPatchLoader` existe mais sa liste de poids est **VIDE** | `QwenImageDiffsynthControlnet`, ~1 Md, Apache-2.0 vérifiée | la **pose**, depuis un croquis ou une illustration existante |

**La marge existe** : après une génération réelle il reste **8,4 à 9,1 Go libres** sur la carte. Un
`MODEL_PATCH` d'environ 1 Md y tient. Ce qui manque n'est pas la place, c'est la mesure de l'apport
— et c'est le `PLAN-30`.

### 7 bis. Ce que le lot 30 a tranché, et ce qu'il n'a pas pu mesurer — 2026-09-03

**Un seul des deux candidats est instrumenté, et le choix ne s'est PAS fait sur l'apport.** Il ne
pouvait pas : l'apport ne se mesure qu'avec un juge étalonné, et le `PLAN-29` a livré son
outillage sans pouvoir l'étalonner. Le choix s'est donc fait sur la **dette d'installation**, qui
est le second critère du plan (étape 0.2) :

| | image de contrôle | entités + masques (EliGen) |
|---|---|---|
| nœud | **intégré à ComfyUI** — `ModelPatchLoader`, `QwenImageDiffsynthControlnet` | **tiers** — `ComfyUI-QwenImageWanBridge` ou `ComfyUI_Qwen-Image` |
| poids | `qwen_image_canny_diffsynth_controlnet.safetensors`, **Apache-2.0 vérifiée le 2026-09-03** | `Qwen-Image-EliGen-V2`, Apache-2.0 vérifiée le 2026-08-30 |
| d'où vient l'entrée | l'utilisateur fournit un trait, un croquis, une silhouette | il faudrait **dessiner un masque** — un éditeur, donc un lot entier |
| dette | aucune | un dépôt tiers de plus à suivre |

« Un canal qui dépend d'un nœud abandonné est une dette » : à apport inconnu des deux côtés, on
instrumente celui qui n'en crée aucune.

**Ce qui est livré** : `illustration/workflows/qwen-image-edit-2511-controle.api.json`, un graphe
**candidat** — jamais exécuté, poids non installé, et qui le dit lui-même dans un bloc racine
`_candidat` que `python tools/comfy.py --valider` affiche. Il ne remplace aucun défaut.

**Ce qui reste à faire, sur le principal :**

```powershell
# 1. déposer le poids sous ComfyUI/models/model_patches/, puis :
python tools/comfy.py --valider illustration/workflows/qwen-image-edit-2511-controle.api.json
# 2. une seule image, pour voir si le patch s'applique au transformeur d'ÉDITION quantifié
# 3. le journal : loaded completely/partially, lowvram patches, pic VRAM, s/image contre 233,7 s
python tools/comfy.py --journal
# 4. l'apport, sur le même banc et le même juge que les références :
python tools/banc_identite.py "<Projet>" <Tome> --personnage "<nom>" --balayage --controle <trait.png> --markdown
```

⚠ **Un `lowvram patches` qui apparaît après l'installation du patch ANNULE la livraison du
canal** — c'est le critère 3 du plan, et il est écrit d'avance pour ne pas être négocié après
coup : le transformeur a été rogné, et le lot 24 a chiffré ce que cela coûte (**facteur 9,6** sur
le pas de débruitage). Un canal qui déclenche le rognage ne se livre pas, même s'il améliore
l'image.

⚠ **La réserve à lever en premier** : le `MODEL_PATCH` est publié pour **Qwen-Image**
(texte-vers-image), et le graphe candidat l'empile sur **Qwen-Image-Edit-2511** quantifié en Q4_1.
Rien n'établit que les deux sont compatibles.

## 8. « Construire un modèle » : ce que ComfyUI ne fait pas

ComfyUI **exécute** des modèles, il n'en **entraîne** pas. Une LoRA de personnage ou de style
s'entraîne ailleurs — `DiffSynth-Studio` documente l'entraînement LoRA et complet pour Qwen-Image —
puis se dépose dans `models/loras/` et se charge par `LoraLoaderModelOnly`.

⚠ **Et ce n'est pas une décision technique.** Entraîner sur les illustrations d'une œuvre sous droits
transforme des images sous droits en poids de modèle : le `PLAN-25` §1 en fait une décision à écrire
dans `docs/ai-provenance.md` **avant** le premier entraînement, avec ses quatre seuils d'abandon.
La voie B n'a pas été ouverte, et le lot 25 a conclu qu'elle n'avait pas à l'être.

---

## 9. Ce que cette fiche ne dit pas

- **Rien ne vaut pour une autre pile.** Tous les chiffres ci-dessus sont liés à ComfyUI 0.34.2,
  ROCm 7.14, RX 7900 XT, `ComfyUI-GGUF`, et aux quatre fichiers de modèle nommés au §0. Sur une
  autre machine, ce sont des **points de départ**.
- **Rien sur la ressemblance d'un personnage.** Le juge automatique du lot 25 ne sépare « même
  personnage » de « personnages différents » que **68 fois sur 100** à un seuil de 80, et le
  protocole humain en aveugle **n'a jamais été exécuté**. Toute colonne « ressemblance » du dépôt
  est marquée **non opposable**. C'est le `PLAN-29`.
- **Rien sur `stable-diffusion.cpp` ni `diffusers`.** Les deux autres chemins que le `PLAN-24`
  demandait de mesurer ne l'ont jamais été.

---

## 10. Quand ça ne marche pas

| Symptôme | Cause mesurée | Ce qu'on fait |
|---|---|---|
| Images brûlées, contrastes saturés | `cfg 4` avec la LoRA Lightning, distillée sans guidage | `guidage: 1.0` et `pas: 4`, ou change de graphe |
| ~64 s **par pas** en texte-vers-image | encodeur sur GPU → transformeur rogné (`lowvram patches`) | `CLIPLoader.device: cpu` — facteur 9,6 |
| `TextEncodeQwenImageEditPlus` ne finit jamais | encodeur sur **CPU** en édition : la tour de vision en fp8 y est émulée | `CLIPLoader.device: default` |
| `Invalid image file: C:\…` | `LoadImage` ne résout que sous `input/` | glisse l'image dans le nœud, ou laisse Angelith téléverser |
| `canal « references » refusé …` | le graphe ne porte pas `%reference_1%` | prends `qwen-image-edit-2511.api.json`, ou ajoute le marqueur |
| Angelith dit que le workflow n'est pas exploitable | export au format écran au lieu du format API | ⚙ → Dev mode → **Save (API Format)** |
| Un modèle n'apparaît pas dans la liste | mauvais dossier, ou serveur non relancé | §2, puis redémarre le serveur |
| 12 Go toujours occupés après un run | `decharger_image: false`, **volontairement** | `POST /free` à la main (⚠ segfaute ~1 fois sur 7) |
| ComfyUI plante en fin de run | le segfault de `/free`, chez ComfyUI | relance le serveur : les images sont déjà écrites et marquées |
| La 1re image est deux fois plus lente | chargement de 12,84 Go + 9,38 Go depuis le disque | normal ; ne la mélange jamais à une médiane |
| Une copie de l'image traîne chez ComfyUI, **non marquée** | le nœud `SaveImage` écrit dans le dossier `output/` de ComfyUI | remplace `SaveImage` par **`PreviewImage`** : la copie va alors dans `temp/`, que ComfyUI vide à son redémarrage, et Angelith la récupère sans changer une ligne. ⚠ **PAS `SaveImageWebsocket`** — ce client ne sait pas le lire, et `--valider` le refuse depuis le lot 30 (2026-09-03) |
| `le nœud « X » n'existe pas sur …` | nœud tiers absent, ou serveur non relancé après l'installation | §7, puis redémarre — `python tools/comfy.py --valider` le dit AVANT le GPU |
| Une image sort étrange et tu ne sais pas pourquoi | le transformeur avait peut-être été rogné pendant CE run | `python tools/comfy.py --journal` : les trois lignes du serveur sont archivées à côté de l'image |
| Tu ne sais pas ce que le projet envoie | — | `python tools/comfy.py --graphe <requete.yaml>`, puis glisse le fichier produit dans ComfyUI |
| Deux runs donnent des images différentes | le graphe a changé entre les deux | `python tools/comfy.py --diff a.api.json b.api.json` — champ par champ, pas ligne par ligne |

⚠ **Six des quinze lignes de ce tableau sont attrapées mécaniquement par
`python tools/comfy.py --valider`, AVANT le GPU** — et `run_illustration.py --check` le fait tourner
tout seul depuis la 2.22.0. Trois autres se diagnostiquent après coup, avec `--journal`, `--graphe`
et `--diff`. Les six restantes sont des comportements du serveur lui-même et ne se voient pas dans
un fichier. Le décompte ligne par ligne est dans `docs/mesures/comfy-visible-2026-09-02.md` §3.

---
