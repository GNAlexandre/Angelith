# Modèles de la brique manga

Ce dossier contient les poids de modèles CV (pas de code source) utilisés par
`manga/detection.py`. Ils ne sont **pas** commités dans le projet (fichiers binaires
volumineux) — à télécharger une fois, en local.

## Détection de bulles (obligatoire) — **rien à faire**

`manga/detection.py` attend un export **ONNX YOLOv8-seg** (format standard
Ultralytics à 2 sorties : boîtes+coefficients de masque, et prototypes de masque).

**Le modèle se télécharge tout seul au premier usage** (~104 Mo, une seule fois),
comme `manga-ocr` le fait déjà pour le sien — piloté par
`config.yaml > manga.detection.telechargement_auto` (`true` par défaut).
`python run_manga.py --check` le récupère aussi, ce qui est le bon moment : au
moment de préparer la machine, pas au milieu d'un tome de 150 planches.

L'écriture passe par un fichier `.part` renommé seulement à la fin : une coupure
réseau, un Ctrl+C ou un disque plein ne laissent **jamais** un `.onnx` tronqué
derrière eux.

Modèle testé et validé pour ce projet — **kitsumed/yolov8m_seg-speech-bubble**
(Hugging Face).

> **Licence : GPL-3.0**, telle que déclarée sur la page du modèle (relevé le 2026-08-25).
> Le dépôt renvoyait à la page du modèle (« licence à vérifier ») : c'est vérifié, et le
> résultat est écrit ici. Une consigne de vérification n'est pas une licence, et personne
> ne peut décider de rediffuser sur la foi d'un renvoi.
> Reporté dans [`docs/ai-provenance.md`](../docs/ai-provenance.md).

- URL : `https://huggingface.co/kitsumed/yolov8m_seg-speech-bubble/resolve/main/model_dynamic.onnx`
- Taille : 108 982 949 octets
- SHA-256 : `36c26bdefe150226acd9669772e9ff5a011fa0dd4622469b49d3d5e359f3251c`
  (relevé le 2026-08-14 ; un écart est signalé sans bloquer, le dépôt amont pouvant
  republier ses poids)

### Récupération manuelle

Utile derrière un proxy, ou avec `telechargement_auto: false` :

```powershell
# Depuis la racine du projet :
New-Item -ItemType Directory -Force manga_models | Out-Null
Invoke-WebRequest -Uri "https://huggingface.co/kitsumed/yolov8m_seg-speech-bubble/resolve/main/model_dynamic.onnx" `
  -OutFile "manga_models/bubble_detector.onnx"
```

Puis vérifie que `config.yaml > manga.detection.model_path` pointe bien vers
`manga_models/bubble_detector.onnx` (c'est déjà la valeur par défaut). Un autre modèle
YOLOv8-seg se substitue via `manga.detection.model_url`.

Ce modèle a été téléchargé et testé pendant le développement de cette brique : sur
une planche de test avec 3 bulles, les 3 sont détectées avec un score de confiance
~0.95 et des boîtes quasi exactes (voir la suite de tests `tests/test_manga_*.py`
pour une validation déterministe indépendante des poids).

## OCR japonais (obligatoire)

`manga/ocr.py` utilise le paquet `manga-ocr` (modèle `kha-white/manga-ocr-base`) :
**aucun téléchargement manuel** — le paquet télécharge son modèle automatiquement
depuis Hugging Face au premier lancement (connexion réseau requise une seule fois,
puis mis en cache localement).

## Inpainting (phase 2, pas encore utilisé)

Réservé au traitement des onomatopées (texte posé directement sur le dessin, qui
nécessite de reconstruire le fond). Pas de modèle requis pour la phase 1 (texte dans
les bulles uniquement, nettoyage par simple remplissage de couleur).

## Détection du TEXTE SUR LE DESSIN (optionnel, lot 9) — **rien à faire**

Onomatopées et narration posées hors des bulles. Même mécanique que ci-dessus : le fichier
se télécharge tout seul au premier usage, par un `.part` renommé à la fin, piloté par
`config.yaml > manga.onomatopees.telechargement_auto`.

Modèle — **`comic-text-detector`** (dmMaze), export ONNX par `mayocream`.

- URL : `https://huggingface.co/mayocream/comic-text-detector-onnx/resolve/main/comic-text-detector.onnx`
- Taille : 94 669 756 octets
- SHA-256 : `1a86ace74961413cbd650002e7bb4dcec4980ffa21b2f19b86933372071d718f`
  (relevé le 2026-08-16 ; un écart est signalé sans bloquer)
- Entrée `[1, 3, 1024, 1024]`, trois sorties : `blk` (boîtes de blocs), `seg` (masque de
  texte dense), `det` (cartes de lignes).

**Seule `seg` est utilisée.** Mesuré sur les planches réelles du Vol.2 de *manga A* : page 63, la
tête `blk` ne propose que 3 boîtes au-dessus de 0,5 — toutes sur du
petit texte horizontal — alors que la colonne de katakana géants qui barre la planche est
parfaitement dessinée dans `seg`. Une tête entraînée sur des *blocs de texte* ne reconnaît
pas un ゴォォォ de 400 px de haut ; un masque par pixel, si. `seg` donne en plus un
**masque**, ce dont l'appariement texte↔bulle a besoin.

⚠ `seg` et `det` sortent **déjà activés** (valeurs dans [0, 1]). Leur appliquer une sigmoïde
— le réflexe hérité de YOLOv8-seg, dont les prototypes sont des logits — ramène tout au-dessus
de 0,5 et déclare 94 % de la planche « texte ».

> ⚠ **Licence.** Le code amont de `comic-text-detector` est **GPL-3.0** et ses poids sont
> entraînés pour partie sur **Manga109-s** (conditions d'usage académique). Vérifie ces
> licences avant tout usage ou diffusion des planches produites.

---

## Un second avis pour l'escalade — évalué, pas intégré (lot 12, L4.7)

Le détecteur actuel n'est **pas remplaçable** : il donne des **masques**, et le nettoyage
déterministe en a besoin (`clean.py` peint le masque, `psd.py` en fait un calque). On n'y
touche pas.

Mais l'escalade de détection (`manga.detection.escalade`) a besoin de pouvoir proposer *autre
chose* qu'un seuil abaissé et une résolution relevée. Deux candidats, relevés le 2026-08-24 :

| Modèle | Sortie | Licence | Corpus déclaré | `imgsize` |
|---|---|---|---|---|
| `kitsumed/yolov8m_seg-speech-bubble` *(actuel)* | bulles, **masques** | **GPL-3.0** | non documenté ; manga | 640 (poids dynamiques) |
| [`ogkalu/comic-speech-bubble-detector-yolov8m`](https://huggingface.co/ogkalu/comic-speech-bubble-detector-yolov8m) | bulles, boîtes | **Apache-2.0** | ~8 000 images, « Manga, Webtoon, Manhua and Western Comic » | **1024** |
| [`ogkalu/comic-text-and-bubble-detector`](https://huggingface.co/ogkalu/comic-text-and-bubble-detector) | `bubble` / `text_bubble` / `text_free` (boîtes, RT-DETR-v2 r50vd) | **Apache-2.0** | ~11 000 images, « **Tall Webtoons were split vertically** » | 640 |

Trois choses à en tirer, la troisième étant la plus importante :

1. Les deux candidats sont **Apache-2.0** et **entraînés sur du webtoon**, ce que le détecteur
   actuel n'est pas. Comme second avis ils coûtent une dépendance de poids et rien d'autre :
   une boîte proposée là où le principal ne voyait rien, dont on dérive un masque par
   remplissage depuis l'intérieur — l'uniformité mesurée par `clean.analyze_bubble` dit déjà
   si ce remplissage est légitime.
2. `comic-text-and-bubble-detector` distingue `text_bubble` de `text_free`. C'est exactement
   l'appariement que `text_detection.hors_des_bulles` reconstruit à la main par containment.
   À évaluer comme simplification — **pas dans ce lot**.
3. **`imgsize: 1024` du premier candidat est un indice, pas une coïncidence.** C'est
   précisément le levier que le lot 12 a rendu configurable côté détecteur actuel
   (`manga.detection.input_size`, et `escalade.input_size: 1024`). Avant d'ajouter 100 Mo au
   projet, il faut savoir ce que la résolution seule a déjà donné.

### Ce qui n'avait PAS été fait au lot 12 — et qui l'a été au lot 16

**L'évaluation n'était pas exécutée** : elle demandait de télécharger des poids tiers, et ce
n'était donc pas un chiffre du lot 12. Le protocole écrit alors est resté celui qu'on a suivi,
et il est reproduit ici tel quel parce que c'est lui qu'il faut relire pour comprendre le
résultat — cf. la section **L'évaluation a eu lieu** en fin de fichier :

1. Exporter les deux candidats en ONNX (Ultralytics pour le premier, RT-DETR pour le second) ;
2. les brancher en **second avis** derrière `detection_retry.arbitrer` — pas en remplacement :
   les boîtes proposées n'existent que si le détecteur principal n'a rien vu ;
3. mesurer sur **les 188 planches à zéro bulle** des dix volumes de `build/`, avec les trois
   indicateurs de fausse détection que le rapport produit déjà (zones restaurées, bulles sans
   texte OCR, bulles non nettoyées) — un gain de bulles payé en faux positifs n'en est pas un ;
4. **mesurer aussi sur le webtoon**, où 24 % des détections sont des zones restaurées : c'est
   là que l'écart a le plus de chances d'être décisif.

### ⚠ Suite : le lot 14 a rempli la condition qui déclenche cette évaluation

Le lot 14 (webtoon) a suivi l'ordre que son plan prescrivait — dédoublonnage de coutures, aire
minimale, fenêtrage du hors-bulle, critère de découpage — en publiant le taux de fausses
détections à chaque étape. Résultat, sur les 9 bandes du chapitre de référence : **22,0 %
→ 15,1–17,0 %**, tout le gain venant du seul dédoublonnage de coutures.

La condition écrite dans le plan était « si le taux reste au-dessus de 5 %, ouvrir le lot 16 ».
**Il y reste, trois fois.** Cette évaluation cesse donc d'être une curiosité et devient la suite
naturelle du travail.

⚠ **Et la réserve qu'on redoutait a été levée, au moins en partie.** Le seul volume webtoon du
dépôt étant aussi son seul volume à **source latine**, ces bulles muettes pouvaient n'être que
des bulles dont `ocr_latin.py` n'a rien tiré — auquel cas changer de détecteur n'y ferait rien.
Le **détecteur de texte**, second modèle étranger au chemin d'OCR, a été interrogé sur un
**crop** de chaque bulle : les muettes couvrent **0,00 %, 0,00 % et 0,41 %** de leur masque en
texte, les témoins lus **3,70 % et 4,08 %**. Elles ne portent rien. La piste est donc bien le
détecteur — c'est-à-dire ce tableau-ci. (Échantillon de 3 contre 2 : cela oriente, cela ne
démontre pas.)

Voir [`docs/mesures/webtoon-2026-08-26.md`](../docs/mesures/webtoon-2026-08-26.md), § 7.

S'il ne gagne rien, on l'écrit et on n'ajoute pas 100 Mo au projet. Le dépôt a déjà cette
discipline — cf. le rejet **mesuré** du repli `use_det=False` dans `manga/ocr_latin.py`.

---

## L'évaluation a eu lieu — lot 16, L9.0 (2026-08-26)

**Les chiffres sont dans [`docs/mesures/detecteurs-candidats-2026-08-26.md`](../docs/mesures/detecteurs-candidats-2026-08-26.md)**,
et l'outil qui les reproduit est `tools/banc_candidats.py`. Ce qui suit n'est que ce qu'il faut
savoir pour **récupérer les poids** — trois faits qui n'étaient pas dans le tableau ci-dessus,
et dont deux le corrigent.

### ⚠ Le premier candidat n'existe pas en ONNX, et il ne s'appelle pas ce qu'il croit

`ogkalu/comic-speech-bubble-detector-yolov8m` ne publie **qu'un `.pt`** — 52 079 361 octets,
SHA-256 `10bc9f70…` relevé le 2026-08-26. Il n'y a aucun export ONNX sur la page du modèle, et
`manga/detection.py` ne lit que de l'ONNX. Il faut donc l'exporter soi-même :

```powershell
# Dans un environnement JETABLE : `ultralytics` tire `opencv-python`, que
# `requirements-manga.txt` refuse (~60 Mo pour trois opérations de morphologie).
python -m venv .venv-export --system-site-packages
.venv-export\Scripts\pip install ultralytics onnx
.venv-export\Scripts\python -c "from ultralytics import YOLO; YOLO('comic-speech-bubble-detector.pt').export(format='onnx', dynamic=True, imgsz=1024)"
```

`dynamic=True` n'est pas optionnel : sans lui l'entrée est figée et
`detection.verifier_axe_dynamique` refuse tout `input_size` différent, ce qui retirerait
justement le levier du lot 12.

Et le fait qui compte : **les noms de classes embarqués dans les poids sont
`{0: "text_bubble", 1: "text_free"}`**, ce qui contredit la fiche du modèle (« speech bubble
detection ») et la ligne « bulles, boîtes » du tableau ci-dessus. Vérifié à la mesure : les
boîtes de classe 0 épousent les **ballons**, pas le texte — sur la page 12 du Vol.1 du manga de
référence, les 12 boîtes coïncident avec les 12 bulles du cache, à quelques pixels près. Ce
sont donc bien des bulles, et les noms sont un reste du fichier `data.yaml` d'entraînement.
Un nom de classe hérité n'est pas un contrat : c'est la mesure qui dit ce qu'un modèle détecte.

### Le second candidat est directement utilisable

`ogkalu/comic-text-and-bubble-detector` publie `detector.onnx` — 168 481 531 octets, SHA-256
`065744e9…` relevé le 2026-08-26. Signature vérifiée :

- entrées `images` `['N', 3, 'H', 'W']` **et** `orig_target_sizes` `['N', 2]` en **(largeur,
  hauteur)** — l'ordre de l'export du dépôt RT-DETR, et non celui de `RTDetrImageProcessor` de
  `transformers`, qui attend `(h, w)`. Se tromper d'ordre décale toutes les boîtes ;
- sorties `labels` / `boxes` / `scores`, boîtes **déjà** en coordonnées de l'image d'origine ;
- prétraitement d'après `preprocessor_config.json` : redimensionnement **plein cadre** en
  640×640 (pas de letterbox, pas de remplissage), `do_rescale: true`, **`do_normalize: false`**
  — ni moyenne ni écart-type. Lui appliquer le letterbox d'Ultralytics mesurerait autre chose
  que le modèle publié ;
- trois classes, `0: bubble`, `1: text_bubble`, `2: text_free`. Seule la classe 0 décrit un
  ballon ; `tools/banc_candidats.py` ne retient qu'elle (`CLASSES_BULLE_RTDETR`).
