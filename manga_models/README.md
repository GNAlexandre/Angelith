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
(Hugging Face, licence à vérifier sur la page du modèle avant tout usage/diffusion).

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

**Seule `seg` est utilisée.** Mesuré sur les planches réelles du Vol.2 de *manga A* : page 63, la tête `blk` ne propose que 3 boîtes au-dessus de 0,5 — toutes sur du
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
