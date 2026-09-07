# Le connecteur Qwen-Image, mesuré sur la 7900XT — ce que seul le réel pouvait montrer

**Date** : 2026-08-29 · **Version livrée** : 2.16.0 · **Branche** : `main`
**Empreinte SHA-256 de `config.yaml`** : `3e93c206a3504f00228d5e7bca77db29bb2edf937ad2d33851765b2d516fc762`
**Machine** : AMD Radeon RX 7900 XT, **20 464 Mio** de VRAM (`21 458 059 264` octets), ROCm 7.14,
Windows 11, 32 678 Mio de RAM
**Pile** : ComfyUI **0.34.2** (standalone `win-amd`, torch 2.12.0+rocm7.14.0, Python 3.13.12),
nœud `ComfyUI-GGUF` (city96, Apache-2.0), `gguf` 0.19.0
**Modèle** : `Qwen-Image-2512` GGUF **Q4_1**, encodeur `Qwen2.5-VL-7B` fp8, VAE `qwen_image_vae`,
LoRA `Qwen-Image-2512-Lightning-4steps` bf16
**Corpus** : `roman S` Vol.1 — bible visuelle du lot 23, 11 personnages, 16 illustrations sources

---

## 1. Ce que ce document referme

La 2.15.0 écrivait, en tête de son propre document de mesure : « **trois des quatre mesures que
le plan demandait n'ont pas pu être faites** », faute de GPU et de réseau. Les trois sont
faites. Ce document les publie, et publie surtout **les six défauts que seul l'usage réel
pouvait montrer** — aucun n'était visible dans 110 tests qui passaient tous.

| Étape du `PLAN-24` | Verdict 2.15.0 | Verdict aujourd'hui |
|---|---|---|
| 0.3 — les trois chemins d'exécution | ❌ non mesurée | ⚠ **ComfyUI mesuré** ; `stable-diffusion.cpp` et `diffusers` toujours non mesurés |
| 0.4 — licences à la source primaire | ❌ non revérifiées | ✅ **revérifiées**, toutes Apache-2.0 |
| 4 — la prémisse « ~10 Go en 4 bits » | ⚠ corrigée sur documents tiers | ✅ **pesée** : 12,84 Go, empreinte vérifiée |
| L24.5 — reproductibilité | ⚠ mécanisme livré, verdict non écrit | ✅ **verdict écrit** (§6) |

---

## 2. La VRAM : le pic est le maximum, pas la somme

C'est la question qui décide de tout sur une carte de 20 Gio, et elle avait une réponse
supposée. Elle a maintenant une réponse relevée dans le journal du serveur :

| Étage | Poids en VRAM | Ce que ComfyUI en fait |
|---|---:|---|
| encodeur de texte `Qwen2.5-VL-7B` fp8 | **7 910 Mio** | chargé, puis **évincé** |
| transformeur Q4_1 | **12 284 Mio** | chargé complètement (`full load: True`) |
| VAE | **241 Mio** | chargé en dernier |
| *somme si tout était résident* | *20 435 Mio* | **ne tiendrait pas** dans 20 464 Mio |
| **pic mesuré pendant un run** | **14 417 Mio** | ✅ marge de 6 047 Mio |

**Les trois se relaient ; ils ne coexistent jamais.** C'est le `model_management` de ComfyUI qui
le fait, pas Angelith — et c'est la seconde bascule du dispositif : la première, celle
d'Angelith, décharge `yume-27b` d'Ollama avant que ComfyUI ne touche à la carte.

### 2.1 — Et le réglage le plus payant du lot est contre-intuitif

Les deux gros modèles tiennent **à 29 Mio près** (20 435 sur 20 464). ComfyUI s'en sort en
rognant le transformeur, et le journal le dit :

```
Unloaded partially: 1921.69 MB freed, 9064.05 MB remains loaded, lowvram patches: 707
```

Le transformeur passe alors en mode « lowvram » et se diffuse depuis la RAM à chaque pas. Même
image, même graine, même prompt :

| `CLIPLoader.device` | Pas de débruitage | Image complète | Pic VRAM |
|---|---:|---:|---:|
| `default` (GPU) | **64,3 s/pas** | ~260 s | 13 799 Mio |
| **`cpu`** | **6,7 s/pas** | **103,7 s** | 14 417 Mio |

**Facteur 9,6 sur l'échantillonnage.** L'encodage sur CPU coûte ~76 s par image, mais il rend
la carte entière au transformeur, et c'est le transformeur qui domine.

⚠ **Le pic est PLUS HAUT dans la bonne configuration** (14 417 contre 13 799 Mio), et ce n'est
pas une contradiction : un pic plus bas décrivait un modèle qu'on avait dû rogner. Un chiffre
de VRAM qu'on lit comme « moins, c'est mieux » se lit à l'envers ici.

---

## 3. Étape 0.3 — le chemin ComfyUI, mesuré

1328 × 1328, graine fixe, cinq prompts distincts issus de la bible réelle.

| Réglage | Pas | Guidage | 1re image | Régime établi (médiane) | Pic VRAM | Échecs |
|---|---:|---:|---:|---:|---:|---:|
| Lightning | 4 | 1,0 | 172,0 s | **103,7 s** · min 100,8 · max 105,7 · sur 4 | 14 417 Mio | **0/5** |
| Référence | 50 | 4,0 | 628,9 s | **629,8 s** · min 565,6 · max 919,7 · sur 4 | 14 421 Mio | **0/5** |

⚠ Le **max de 919,7 s** du réglage 50 pas est un artefact de mesure honnête : un rejeu à 4 pas
a été mis en file au milieu du banc, forçant un rechargement de modèle. Il est gardé dans la
série plutôt que retiré, et signalé — écarter une valeur gênante sans la nommer serait
exactement ce que ce dossier reproche ailleurs.

⚠ **La première image d'une session n'est pas comparable** : elle paie le chargement des poids
depuis le disque (12,84 Go + 9,38 Go). Elle est relevée à part, jamais mélangée à la médiane.

**Sur le run de production** (`roman S` Vol.1, 11 images d'affilée, mêmes réglages Lightning) :
**116,1 s par image en moyenne**, 1 277,3 s au total, **0 échec sur 11**. La moyenne dépasse la
médiane du banc parce qu'elle inclut la première image (189,2 s).

### 3.1 — Le prix des 50 pas : 6,1 fois, pas 12,5

Le rapport de pas est de **12,5** (50 contre 4) ; le rapport de temps mesuré est de **6,1**
(629,8 / 103,7). Deux effets se composent, et aucun n'est un détail :

- **le guidage double le travail par pas.** À `cfg > 1`, ComfyUI fait deux passes avant par pas
  — conditionnée et non conditionnée — pour le guidage libre de classifieur. Mesuré dans le
  journal : **6,7 s/pas à `cfg 1,0`** contre **9,7–10,05 s/pas à `cfg 4,0`** ;
- **un coût fixe d'environ 76 s par image** — encodage du texte sur CPU, chargement du VAE,
  décodage — qui domine une image de 4 pas (27 s d'échantillonnage) et disparaît dans une de
  50 pas (~500 s).

D'où `103,7 ≈ 76 + 27` et `629,8 ≈ 76 + 500`. **Ce que 50 pas achètent est mesuré au §8.1 :
24 % d'écart de style en moins, et rien du tout sur la densité de trait.**

### 3.1 bis — Le taux d'échec, sur l'ensemble de la session

Le `PLAN-24` demandait « le taux d'échec sur 20 images ». Sur **25 générations** enchaînées ce
jour-là — 1 essai manuel, 5 du banc Lightning, 11 du run de production, 1 rejeu, 5 du banc à
50 pas, plus 2 essais interrompus — :

| | |
|---|---:|
| générations exécutées par ComfyUI | **25** |
| échecs d'exécution (erreur de nœud, OOM, HIP) | **0** |
| images écrites sur disque | **22** |
| dont **écrites et marquées par la brique** | **12** (11 du run + 1 rejeu) |
| dont écrites brutes par le script de banc | 10 |

⚠ **Les 10 images de banc ne portent aucun marquage, et c'est normal** : le script de mesure
n'est pas la brique, il écrit les octets rendus par le moteur directement dans le scratchpad.
Elles ne sortent pas de `illustration/marquage.py` et n'ont donc ni bloc `tEXt` ni sidecar. Le
critère 7 du `PLAN-24` porte sur ce que **la brique** produit, et les 12 images qui en sortent
sont marquées à 12 sur 12.

⚠ **Deux erreurs figurent bien dans le journal du serveur**, et ce n'en sont pas : ce sont les
deux HTTP 500 provoqués par le défaut §7.3 (une clé de commentaire à la racine du workflow),
survenus **avant** la première génération et corrigés avant qu'une seule image ne soit
produite. Les compter comme des échecs de génération serait faux ; ne pas les mentionner le
serait aussi.

### 3.2 — Les deux chemins NON mesurés, et ils le restent

`stable-diffusion.cpp` et `diffusers` n'ont pas été essayés. Le `PLAN-24` demandait les trois ;
il y en a **un**. Le motif d'abandon publié en 2.15.0 tenait sur le critère de dépendance —
« combien de dépendance le dépôt avale-t-il ? » — et il n'a pas changé : le chemin retenu
n'ajoute **rien** à `requirements-*.txt`, l'utilisateur installant ComfyUI lui-même comme il
installe Ollama.

⚠ Ce n'est pas une comparaison, c'est un choix justifié autrement. Le dire vaut mieux que de
présenter un tableau à une ligne comme un banc à trois.

---

## 4. Étape 0.4 — les licences, revérifiées à la source primaire

Interrogé le 2026-08-29 sur l'API Hugging Face :

| Dépôt | Licence déclarée | Usage |
|---|---|---|
| `Qwen/Qwen-Image-2512` | **apache-2.0** | modèle amont |
| `Comfy-Org/Qwen-Image_ComfyUI` | **apache-2.0** | encodeur de texte, VAE |
| `unsloth/Qwen-Image-2512-GGUF` | **apache-2.0** | transformeur Q4_1 |
| `lightx2v/Qwen-Image-2512-Lightning` | **apache-2.0** | LoRA 4 pas |
| `city96/ComfyUI-GGUF` | **Apache-2.0** (fichier `LICENSE`) | nœud de chargement |

⚠ **C'est la licence DÉCLARÉE par le dépôt amont**, relevée à sa source, et non un avis
juridique sur la licence des poids eux-mêmes. La jurisprudence du dépôt — « licence du code
Apache-2.0 ne dit rien de la licence des poids » — reste la bonne façon de lire ce tableau :
ici, c'est bien le champ licence du dépôt **de poids** qui est relevé, ce qui est le mieux
qu'une vérification automatique puisse établir.

⚠ **Aucune URL n'est pour autant codée en dur dans le dépôt.** La règle de la 2.15.0 tient :
`illustration.poids.url` reste vide, et l'utilisateur renseigne ce qu'il a vérifié.

---

## 5. La prémisse « ~10 Go en 4 bits », enfin pesée

| Ce qu'on mesure | Valeur | Comment |
|---|---:|---|
| `qwen-image-2512-Q4_1.gguf` | **12 843 678 240 octets** (12,84 Go / 11,96 Gio) | `stat` |
| SHA-256 | `a4cc72564b4c3422ec9771b257d9de0e498d4f4226a5b42d86ac1f24998686ad` | calculé en **13 s** |
| Vérification amont | ✅ | Hugging Face nomme ses blobs par leur SHA-256 : le nom du blob **est** l'empreinte |
| encodeur de texte fp8 | 9 384 670 680 octets (9,38 Go) | API HF |
| VAE | 253 806 246 octets (0,25 Go) | API HF |
| LoRA Lightning bf16 | 849 608 296 octets (0,85 Go) | API HF |

**« ~10 Go » désignait le transformeur seul et le sous-estimait de 28 %.** Le total réel des
poids sur disque est **23,3 Go**, et la grandeur qui décide — le pic de VRAM — vaut
**14 417 Mio**, ce qu'aucune taille de fichier ne permettait de deviner.

---

## 6. L24.5 — la reproductibilité, et elle est meilleure qu'annoncé

Le critère du plan : « deux exécutions de la même `Requete`, même graine, même modèle, même
`config.yaml`, produisent deux PNG identiques octet pour octet — **ou l'écart est mesuré et
expliqué** ». Le lot 24 avait pris soin d'écrire que la seconde branche était la plus probable,
« la plupart des backends de diffusion ne sont pas déterministes ».

**Sur cette pile, la première branche tient.**

```
python run_illustration.py --rejouer build/…/major-lenvil.png.provenance.json
  → octet pour octet identique à l'original.
```

| Contrôle | Valeur |
|---|---|
| SHA-256 de l'original | `89745b1b12b34365c902a729a6df2d1cce6c4622875ad25061424a271b15efee` |
| SHA-256 du rejeu | `89745b1b12b34365c902a729a6df2d1cce6c4622875ad25061424a271b15efee` |
| empreinte de requête | identique |
| le rejeu porte son marquage | `AIGenerated=true`, et son sidecar nomme `rejeu_de` |

⚠ **Le dénominateur est de UN.** Une requête rejouée une fois, pas « 5 requêtes × 3
exécutions » comme le plan le demandait. C'est un résultat encourageant, ce n'est pas encore
une propriété du backend : il faudrait au minimum varier les prompts et les graines avant
d'écrire « ComfyUI est déterministe » sans guillemets.

⚠ **Et il est conditionné à la pile.** Même GPU, même version de ROCm, même ordre de
chargement. Un déterminisme bit-à-bit sur une carte donnée ne dit rien du même calcul sur une
autre.

---

## 7. Les six défauts que 110 tests verts n'ont pas vus

Aucun des six n'était visible en CI.
Un septième manque — non pas un défaut mais une moitié absente — est traité au §7.6 bis. Chacun est corrigé **et** couvert par un test neuf qui
aurait échoué avant.

### 7.1 — Un téléchargement réussi bouclait jusqu'à l'abandon

`illustration/poids.py` écrivait `total = total or (longueur + deja)` : une estimation
`octets_attendus` n'était **jamais** corrigée par le `Content-Length` du serveur. Sur le VAE,
l'estimation dépassait le fichier réel de **166 octets** — le fichier était intégralement reçu,
se croyait incomplet, redemandait un `Range` au-delà de la fin, et recevait **HTTP 416**, trois
fois, puis abandonnait. Sur un fichier de 12 Go, ce défaut aurait coûté un après-midi.

Deux corrections : `Content-Length` fait foi, et **416 est lu pour ce qu'il est** — « tu as
déjà tout le fichier ». Vérifié sur le réel : le VAE s'est terminé **en 0 s** depuis son
`.part` complet au run suivant.

### 7.2 — Le corps des erreurs HTTP était jeté

Le premier appel réel a rendu « HTTP Error 500: Internal Server Error » et rien d'autre. Il a
fallu ouvrir le journal du serveur pour une cause qui tenait en une ligne. Le corps de la
réponse — qui porte le `node_errors` nommant le nœud et le champ fautifs sur un 400 — est
maintenant relayé dans le message.

### 7.3 — Un commentaire dans un workflow faisait tomber ComfyUI

ComfyUI itère sur **toutes** les clés racine du graphe et appelle `.get('_meta')` sur chacune.
Une clé `_commentaire` dont la valeur est une liste produit un `AttributeError`, rendu au
client en 500 opaque. Le dépôt vit de fichiers commentés — `config.yaml` est « un document » —
donc on garde le droit de commenter, et **c'est le client qui nettoie** juste avant l'envoi :
un nœud est un objet portant `class_type`, tout le reste est de la prose.

### 7.4 — Deux règles de résolution des références coexistaient

`core/bible.py` accepte une référence existant sous **n'importe quel** tome du projet — la
bible est **par projet** — et `illustration/requete.py` en avait écrit une seconde qui ne
cherchait que sous le tome courant. Sur `roman S`, **7 des 10 références vivent dans le Vol.2** et
étaient donc déclarées introuvables, ce qui bloquait la phase image sur un corpus sain.

`core.bible.reference_existe` devient publique et devient **la** règle. Deux règles, c'était
une de trop.

### 7.5 — Le prompt ignorait le champ central de la bible

Vu à l'œil sur le premier run : **« Gale », décrit « adulte, cheveux courts foncés, uniforme
militaire », est sorti en femme.** `genre_confirme` — le champ dont `core/glossary.py` dit
lui-même qu'il commande les accords, et pour lequel le lot 23 existe — n'entrait pas dans le
prompt assemblé.

Il y entre désormais, **accordé** (« un homme seul » / « une femme seule »), et **seulement
s'il est confirmé** : `core/bible.py` note qu'« une valeur fausse ici coûte plus qu'une valeur
absente », donc l'abstention reste le défaut.

⚠ **Et le correctif ne change rien sur `roman S` aujourd'hui** : les **11 personnages sur 11**
ont `genre_confirme` vide. Le code est réparé ; le corpus n'en profite pas encore. C'est
exactement l'écart que le `PLAN-23` avait relevé à l'échelle du dépôt.

### 7.6 — Un commentaire pouvait déclarer un canal que le workflow n'honore pas

**Le plus grave des six, parce qu'il rouvrait la porte que tout le dispositif ferme.**

`CANAUX_SUPPORTES` se lisait dans le **texte brut** du fichier de workflow. Or le commentaire
du graphe de référence livré ici écrit, en toutes lettres, qu'il ne porte « NI `%reference_1%`
NI `%masque_1%` NI `%image_controle%` ». Le scan y voyait les trois marqueurs et déclarait les
trois canaux **supportés**.

Conséquence : le moteur aurait accepté une requête portant des images de référence et les
aurait **jetées en silence**, produisant une image plausible et fausse — précisément le défaut
que le critère 7 bis du `PLAN-24` existe pour empêcher, réintroduit par une ligne de
documentation.

Trouvé en relisant les deux workflows après les avoir écrits, pas par un test. Les canaux se
lisent désormais dans les **nœuds** seuls, et deux tests le gardent : l'un sur un commentaire
piégé, l'autre sur les deux workflows réellement livrés.

### 7.6 bis — La seconde moitié de la bascule manquait, et elle ne peut pas être armée

Question posée après coup : *comment décharger le modèle ?* Elle a révélé que **la brique ne le
faisait pas**, alors que le `README-ILLUSTRATION-23-27` §4 bis décrit le cycle complet —
« déchargement du LLM → génération → **le modèle d'image est déchargé, le LLM peut revenir** ».
Angelith faisait la première moitié et pas la seconde : **12 083 Mio** restaient occupés après
un run, et un `run.py` lancé derrière trouvait la carte prise.

Le mécanisme est ajouté (`Moteur.decharger`, `illustration.vram.decharger_image`). **Il est
livré DÉSARMÉ**, et c'est une mesure qui le décide :

| Appels à `/free` de ComfyUI | Résultat |
|---:|---|
| 7 | 6 succès — 12 083 Mio → **~470 Mio** en quelques secondes |
| | **1 segfault de ComfyUI** — `0xC0000005` dans son propre `comfy/model_management.py:model_unload`, via `free_memory` et `unload_all_models` |

**1 sur 7.** Le plantage est **dans ComfyUI**, sous ROCm 7.14 / Windows ; Angelith ne peut pas
le corriger. Il ne coûte aucune image — elles sont écrites et marquées avant cet appel — mais
il coûte un redémarrage du serveur, et c'est une surprise qu'on n'impose pas par défaut.

C'est la règle du dépôt appliquée telle quelle : **livrer désarmé ce que la mesure ne soutient
pas**, comme `manga.onomatopees.effacement.mode: "aucun"` au lot 22. La commande manuelle est
dans `docs/COMMANDES.fr.md`, et fermer ComfyUI rend la carte sans ce risque.

⚠ **Un piège de la commande manuelle, vérifié** : sous PowerShell 5.1, `curl.exe` ne parvient
pas à transmettre le corps JSON quelle que soit la forme d'échappement — ComfyUI répond
`HTTP 500` sur un `json.loads` qui échoue. C'est `Invoke-RestMethod` qu'il faut.

### 7.7 — Deux améliorations qui découlent des mêmes runs

- **les canaux sont vérifiés AVANT la bascule VRAM.** Refuser un canal après avoir déchargé le
  LLM et chargé 12 Go coûtait plusieurs minutes pour une erreur connue d'avance ;
- **le déchargement LLM ne compte plus deux fois le même modèle.**
  `core/cli.py:models_in_config` dédoublonne dans une section, pas entre deux, et
  `modeles.traducteur` / `manga.modeles.manga_traducteur` nomment le même `yume-27b`. Mesuré :
  **4,22 / 4,14 / 4,05 s** à deux appels contre **2,03 s** à un seul. Le run de production a
  effectivement basculé en **2,1 s**.

---

## 8. Le résultat négatif, et il est mesuré

**Les images produites ne sont pas dans le registre graphique du tome.** Ce n'est pas une
impression : c'est l'outil du lot 23 (`core/illustrations.py:signature`) appliqué aux deux
ensembles, avec les mêmes règles.

| Descripteur | Tome (16 illus.) | Généré (11 img.) | Écart |
|---|---:|---:|---:|
| saturation moyenne | 0,0661 | **0,3231** | 0,257 |
| contraste | 0,2421 | 0,1481 | 0,094 |
| densité de trait | **0,2664** | **0,0522** | 0,214 |
| part d'aplats | 0,3669 | 0,6016 | 0,235 |
| **régime de couleur** | **noir et blanc** | **couleur** | **✗** |
| | | | **moyenne 0,200** |

Palette dominante du tome : `#f0f0f0 #d0d0d0 #b0b0b0 #303030 #505050` — des gris.
Palette dominante des générations : `#101010 #505030 #303030 #707050 #505050`.

Le tome est **au trait et en noir et blanc** ; les générations sont **photographiques et en
couleur**, avec **cinq fois moins de trait**. Ni le prompt assemblé ni les workflows livrés ne
portent d'ancrage de style — c'est la moitié « registre graphique » que le
`README-ILLUSTRATION-23-27` §4 quater annonçait, et c'est la matière du `PLAN-25`.

### 8.1 — Et le calcul n'y peut rien : 50 pas ne rapprochent pas du registre

La même mesure, appliquée aux images à 50 pas, tranche une question qu'on pouvait légitimement
se poser — « est-ce que les 4 pas de la LoRA appauvrissent le rendu au point de le sortir du
registre ? »

| Descripteur | Tome (16) | **4 pas** (11) | **50 pas** (4) |
|---|---:|---:|---:|
| saturation moyenne | 0,0661 | 0,3231 | 0,2658 |
| contraste | 0,2421 | 0,1481 | 0,1751 |
| **densité de trait** | **0,2664** | **0,0522** | **0,0536** |
| part d'aplats | 0,3669 | 0,6016 | 0,4974 |
| régime de couleur | noir et blanc | couleur | couleur |
| **écart moyen au tome** | — | **0,200** | **0,1525** |

**5,4 fois plus de calcul achète 24 % d'écart moyen en moins — et rien du tout sur le trait.**
La densité de trait passe de 0,0522 à 0,0536 : identique à la mesure près, et toujours **cinq
fois** sous celle du tome. Le régime de couleur reste faux dans les deux cas.

⚠ **La conclusion est donc plus forte qu'un simple « il faudra travailler le style » :** le
registre graphique n'est pas un problème de nombre de pas, et **aucune quantité de calcul ne le
résoudra**. Il faudra un ancrage — prompt de style, images de référence de style, ou LoRA — et
c'est exactement ce que le `PLAN-25` a à décider.

⚠ Le dénominateur du 50 pas est de **4 images** contre 11 pour le 4 pas. L'écart de 0,1525
porte ce petit échantillon.

⚠ **Un second écart, visible et non mesuré** : le prompt demande un portrait « en pied », et
les 11 images sont des **plans poitrine**. La forme du texte est l'étape 0.3 du `PLAN-26`.

✅ **Un contrôle croisé qui, lui, est bon** : la signature stockée dans `bible.yaml` par le lot
23 se recalcule **à l'identique** (0,0661 / 0,2421 / 0,2664 / 0,3669) à partir des images du
tome. La mesure du lot 23 est reproductible.

---

## 9. Ce que la mesure ne dit toujours pas

1. **Rien sur la ressemblance d'un personnage.** Aucune image de référence n'a été utilisée :
   les workflows livrés sont texte-vers-image, et le moteur **refuse** le canal `references`.
   La ressemblance est le `PLAN-25`, et elle n'est pas entamée.
2. **Rien sur `stable-diffusion.cpp` ni sur `diffusers`.** Un chemin mesuré sur trois.
3. **Rien sur une autre pile.** Les deux workflows livrés sont liés à ComfyUI 0.34.2, au nœud
   `ComfyUI-GGUF` et à quatre fichiers de modèle nommés. Ailleurs, ce sont des points de
   départ, pas des garanties.
4. **Rien sur la qualité perçue.** Aucune des 11 images n'a été jugée par un œil humain sur
   autre chose que le registre graphique. « Ressemble au personnage » n'est pas mesuré ici.
5. **L'échantillon est petit** : 16 illustrations sources contre 11 générations, un seul tome,
   un seul projet. L'écart de style de 0,200 porte ce dénominateur et pas un autre.
6. **Une copie NON MARQUÉE reste chez ComfyUI.** Le nœud `SaveImage` écrit dans le dossier de
   sortie de ComfyUI ; Angelith récupère l'image, la marque, et l'écrit dans son dossier. La
   copie de ComfyUI ne porte ni `tEXt` ni sidecar. La frontière d'Angelith couvre **ses**
   écritures, pas celles d'un programme tiers lancé par l'utilisateur — et le dire vaut mieux
   que de laisser croire le marquage universel.
7. **`genre_confirme` est vide sur 11 personnages sur 11** de la bible réelle. Le correctif de
   §7.5 est vérifié par test, **pas** par une image de `roman S`.

---

## 10. Ce qui tient, et se vérifie sur le réel

Toutes ces vérifications portent sur le **corpus réel**, pas sur un arbre témoin.

| Propriété | Vérification | Verdict |
|---|---|---|
| la frontière d'écriture | **264 fichiers** du tome hors brique, **0 modifié** après 11 générations | ✅ |
| `RAPPORT.md` et `perf.log` du tome | horodatages inchangés | ✅ |
| `.checkpoints/` | **227 fichiers**, **0 modifié** — interdit n° 1 tenu | ✅ |
| la porte humaine | `valide: false` refusé, puis validé, puis produit | ✅ |
| le marquage | 7 champs `tEXt` + sidecar sur 11 images sur 11 | ✅ |
| le titre hors métadonnées | « roman S » absent des PNG, sidecars et rapport | ✅ |
| le refus de canal | `references` refusé, motif nommé, **0 s de GPU dépensée** | ✅ |
| l'empreinte des poids dans le sidecar | `a4cc7256…`, identique à l'amont | ✅ |
| la bascule VRAM une fois par run | 2,1 s, publiée à côté du prix d'une image | ✅ |
| le rapport de la brique | écrit dans son dossier, celui du tome intact | ✅ |
