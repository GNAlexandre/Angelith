# Poids du modèle d'image — ce qui est établi, et ce qui ne l'est pas

Ce dossier reçoit les poids de la brique **illustration** (`run_illustration.py`). Il est vide
à l'installation, et il le reste tant que personne ne demande explicitement un téléchargement :
`illustration.poids.telechargement_auto` vaut `false`, à l'inverse de la brique manga, et la
raison est le facteur cent — 104 Mo pour le détecteur de bulles, 11,9 à 13,1 Go pour un GGUF
Q4 de `Qwen-Image-2512`.

`.gitignore` couvre `*.gguf`, `*.safetensors`, `*.ckpt` et `*.part` ; ce `README.md` est le
seul fichier du dossier qui entre dans l'arbre.

---

## ⚠ Aucune URL n'est codée en dur dans le dépôt, et c'est délibéré

`manga/models.py` porte `DETECTEUR_URL`, `DETECTEUR_SHA256` et `DETECTEUR_OCTETS` en
constantes. `illustration/poids.py` n'en porte aucune. Ce n'est pas une incohérence, c'est
l'application de la jurisprudence du dépôt :

> `docs/mesures/detecteurs-candidats-2026-08-26.md` et le `PLAN-22` l'ont établie — **la
> licence des poids se vérifie à la source primaire**, et « licence du code Apache-2.0 » ne
> dit rien de la licence des poids.

La session qui a livré le lot 24 **n'avait pas d'accès réseau** : elle n'a donc pas pu
revérifier une seule des lignes du tableau ci-dessous à sa source. Coder une URL et une
empreinte dans le dépôt aurait transformé une vérification **non faite** en fait acquis du
code. Le tableau est donc reproduit avec sa date d'origine et son statut, et c'est
l'utilisateur qui renseigne `illustration.poids.url`, `illustration.poids.fichier` et
`illustration.poids.sha256` après avoir vérifié lui-même.

Le projet est **AGPL-3.0** et utilise déjà des poids sous contrainte (détecteur de bulles,
`comic-text-detector` + Manga109-s académique). Ajouter un poids dont la licence est inconnue
serait le premier de la série à ne pas avoir de justification écrite.

## Les candidats, tels que relevés le 2026-08-27 — **à revérifier avant usage**

| Candidat | Ce qu'il apporte | Statut au 2026-08-27 | Revérifié ? |
|---|---|---|---|
| `Qwen-Image-2512` (20 Md) | texte-vers-image pur ; rendu de texte amélioré | **Apache-2.0** annoncé, sorti le 2025-12-31. **Ne conditionne sur aucune image de référence** — il ne résout donc pas « le bon personnage » à lui seul | ❌ non |
| `Qwen-Image-Edit-2511` (20 Md) | **plusieurs images de référence**, « character consistency significantly improved » | **Apache-2.0** annoncé, sorti le 2025-12-23. C'est le candidat naturel du `PLAN-25` | ✅ **oui, le 2026-08-29** — apache-2.0 déclaré par `Qwen/Qwen-Image-Edit-2511` et par `unsloth/Qwen-Image-Edit-2511-GGUF`. **Utilisé** par le lot 25 |
| `Qwen-Image-2.0` (7 Md) | 2K natif, génération + édition unifiées ; **7 Md tiendraient dans 20 Go sans quantisation agressive** | **Licence non établie** — la page Hugging Face répondait 401 le 2026-08-27. **Sans licence claire, on ne l'utilise pas** | ❌ non |
| `Qwen-Image-EliGen-V2` (LoRA 0,2 Md) | contrôle par **entités** — position et forme de chaque élément | **Apache-2.0** annoncé | ❌ non |

## La prémisse « environ 10 Go en 4 bits », et son dénominateur

Elle est **corrigée, pas confirmée**, et l'erreur n'est pas dans le chiffre : elle est dans ce
qu'il compte.

| Ce qu'on mesure | Valeur relevée le 2026-08-27 | Source |
|---|---|---|
| GGUF Q4_0 / Q4_K_S du transformeur de `Qwen-Image-2512` | **11,9 – 12,3 Go** | guide GGUF publié (dev.to) |
| GGUF Q4_K_M du même transformeur | **13,1 Go** | idem |
| GGUF Q8_0 | 21,8 Go | idem |
| Encodeur de texte `Qwen2.5-VL-7B` | **non compté ci-dessus** | idem |
| VAE | **non compté ci-dessus** | idem |

Autrement dit : « ~10 Go » désigne le **transformeur seul**, en dessous de la fourchette
réelle, et la **VRAM résidente** — transformeur + encodeur de texte + VAE + activations — n'a
pas de chiffre établi. C'est précisément pour ça que le budget compte :

> `docs/README.fr.md` (≈ l. 639) : « ~17 Go ne tiennent de toute façon pas dans 20 Go de VRAM.
> Ça supprime tout scénario de seconde instance / partage de VRAM. »

D'où la conclusion structurelle du lot, écrite dans le code et pas seulement ici : **la
génération d'image et la traduction ne coexistent jamais en VRAM.** La bascule passe par
`core/power.py:ollama_unload`, qui existait déjà et qui est réutilisé.

⚠ **Aucune de ces valeurs n'a été relevée sur la 7900XT.** Ce sont des chiffres publiés par des
tiers, avec leur date ; le pic de VRAM réel, le temps par image et le taux d'échec sur 20
images sont l'étape 0.3 du `PLAN-24`, et elle **n'est pas faite**
(`docs/mesures/socle-generatif-2026-08-29.md` §3).

## Installer un poids à la main

```powershell
# 1. vérifie la licence À LA SOURCE, note l'URL et la date
# 2. renseigne config.yaml > illustration.poids.{fichier,url,sha256}
# 3. puis, au moment où tu prépares la machine — jamais au milieu d'un tome :
python run_illustration.py --check --telecharger
```

Le téléchargement écrit un `<nom>.part`, **reprend** sur coupure par une requête `Range`, et ne
renomme le fichier qu'après vérification de l'empreinte. Une empreinte qui ne correspond pas
est une **erreur** ici, là où `manga/models.py` se contente d'un avertissement : un ONNX
corrompu se voit à la première inférence, un GGUF de 12 Go mal repris produit du **bruit
plausible**, et coûterait une soirée de diagnostic.


---

# Lot 25 — le juge, et le modèle d'édition

## Le juge : un encodeur d'image ONNX

Le `PLAN-25` mesure la ressemblance avec un encodeur d'image, pas avec un œil. Le dépôt n'en
livre aucun : `illustration.identite.encodeur.fichier` est **vide par défaut**, exactement
comme `illustration.poids.fichier`, et pour la même raison.

| Ce qui a été utilisé pour la mesure du 2026-08-29 | Valeur |
|---|---|
| dépôt | `onnx-community/dinov2-base`, fichier `onnx/model.onnx` |
| taille | **346 627 111 octets** |
| SHA-256 | `320d1012a6fc65b101fc85ca30ee7a47b2e4f6a2e8bd78fb9d7036def0e30cb0` |
| **licence déclarée par ce dépôt** | **AUCUNE** — le champ est vide |
| licence de la source amont | `facebook/dinov2-base` déclare **apache-2.0** |
| coût mesuré | **0,31 s par image** sur CPU à 224 × 224 ; 97 images encodées en ~50 s |

⚠ **Le réexport ONNX ne déclare pas de licence, et l'amont oui.** C'est la jurisprudence du
dépôt prise à l'envers : d'habitude c'est le code qui est sous licence claire et les poids qui
ne le sont pas ; ici c'est la republication qui est muette. Le lot 25 s'en sert pour **mesurer**
et non pour produire, il ne redistribue rien, et le fichier est gitignoré (`*.onnx`) — mais la
ligne est écrite plutôt que passée sous silence.

## ⚠ Un piège vérifié, qui a coûté deux téléchargements

L'**`ETag`** que rend une requête HTTP sur `huggingface.co/<dépôt>/resolve/main/<fichier>`
n'est **pas** le SHA-256 du fichier : la requête suit une redirection vers le CDN, et c'est
l'empreinte du CDN qui revient. Seul `lfs.sha256` de l'API l'est :

```powershell
# La SEULE empreinte qui décrit le fichier
curl.exe -s "https://huggingface.co/<dépôt>/api/models/<id>?blobs=true"
```

Le garde d'empreinte de `illustration/poids.py` a refusé les deux fichiers sur cette confusion,
**et il a eu raison de le faire** : le `.part` a été conservé, et relancer avec la bonne
empreinte a terminé en 0,3 s pour l'encodeur et 12,5 s pour le GGUF de 12,8 Go.

## Le modèle d'édition, et ce qu'il coûte

| Fichier | Octets | SHA-256 (`lfs.sha256`) | Licence déclarée |
|---|---:|---|---|
| `unsloth/Qwen-Image-Edit-2511-GGUF` → `qwen-image-edit-2511-Q4_1.gguf` | 12 843 678 304 | `ea5e56e5b729ee642960914aa69b7ef1ac973ad123397f6b93f9acdac5ab9160` | **apache-2.0** |
| `lightx2v/Qwen-Image-Edit-2511-Lightning` → `…-4steps-V1.0-bf16.safetensors` | 849 608 296 | `22226e8d05d354bb356627d428809f5afd7819399b077238a2b70a82883a904f` | **apache-2.0** |

Il réutilise l'encodeur de texte et le VAE déjà installés pour `Qwen-Image-2512` : le coût
disque du lot 25 est donc de **13,7 Go**, pas de 23 Go.

⚠ **Ces deux fichiers ne vont PAS dans ce dossier** : ils vont dans les dossiers de modèles de
ComfyUI (`models/unet/` et `models/loras/`), parce que c'est ComfyUI qui les charge. Ce dossier
reçoit ce qu'**Angelith** charge lui-même — aujourd'hui, l'encodeur du juge et rien d'autre.
