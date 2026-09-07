# Procédure — manga et webtoon (`run_manga.py`)

Détecter les bulles d'une planche, les nettoyer, en lire le texte, le traduire et le
relettrer, sans jamais que l'IA dessine.

> **Le principe directeur, en une phrase.** Détection et OCR ne font que **lire** l'image. Les
> seules écritures de pixels sont déterministes : `manga/clean.py` remplit le masque de bulle
> détecté avec sa couleur de fond mesurée, `manga/typeset.py` y dessine le texte traduit avec
> Pillow. Aucun modèle génératif ne touche au dessin, et un test le vérifie au pixel près.

---

## 1. Poser les planches

```
sources/<Œuvre>/<Chapitre>/<LANGUE>/001.png, 002.png…        ← manga paginé
sources/<Œuvre>/<Chapitre>/webtoon/<LANGUE>/1.png, 2.png…    ← webtoon (bandes verticales)
```

Le glossaire est **le même fichier que celui du light novel** :
`sources/<Œuvre>/glossaire.yaml`, au niveau de l'œuvre.

## 2. Vérifier avant de dépenser du GPU

```powershell
python run_manga.py --check                        # poids ONNX, manga-ocr, polices, LLM, pack
python run_manga.py --list                         # les œuvres
python run_manga.py "Mon Manga" --list             # les chapitres
python run_manga.py "Mon Manga" Vol.1 --dry-run    # détection et OCR RÉELS, aucun appel LLM
```

`--dry-run` est le bon geste ici : il fait tourner tout ce qui coûte du calcul local
(détection, nettoyage, OCR) et ne dépense pas le LLM. C'est là qu'on voit si la détection tient.

## 3. Traduire

```powershell
python run_manga.py "Mon Manga" Vol.1
python run_manga.py "Mon Manga" Vol.1 --lot 20              # 20 planches par appel LLM
python run_manga.py "Mon Manga" --all                       # tous les chapitres restants
python run_manga.py "Mon Manga" --all --keep-awake --shutdown
python run_manga.py "Mon Webtoon" Chap.11 --format webtoon
```

Sept étapes : **`detection` → `nettoyage` → `ocr` → `terminologie` → `traduction` → `sfx` →
`rendu`**.

```powershell
python run_manga.py "Mon Manga" Vol.1 --from rendu        # relettrer seulement, 0 appel LLM
python run_manga.py "Mon Manga" Vol.1 --from traduction   # retraduire puis relettrer
python run_manga.py "Mon Manga" Vol.1 --page 3            # une seule planche
python run_manga.py "Mon Manga" Vol.1 --page 3 --from ocr
python run_manga.py "Mon Manga" Vol.1 --stop              # arrêt propre (autre terminal)
```

⚠ En mode `--all`, **un chapitre complet et à jour n'est même pas ouvert** (629 ms pour le
constater, contre 3 min 9 s pour rouvrir trois chapitres). `--from rendu` et `--force`
**annulent ce saut** — sans quoi une harmonisation de l'œuvre ne toucherait aucun chapitre
fini, c'est-à-dire exactement ceux qu'elle vise.

## 4. Régler la détection sur une planche, avant de payer le tome

```powershell
python tools/apercu_detection.py "Mon Manga" Vol.1 --page 3
python tools/apercu_detection.py "Mon Manga" Vol.1 --page 3 --resolutions --balayage
```

L'outil n'écrit rien et ne touche à aucun cache. La ligne « la planche occupe N px du
canevas » est celle qui décide : en dessous du seuil, la planche est découpée en fenêtres.

## 5. Lire ce qui est sorti

```
build/<Œuvre>/<Chapitre>/
├── manga/pages_src/  pages_clean/  pages_out/
├── <Œuvre>_<Chapitre>.cbz  (+ .psd, images)
├── RAPPORT.md         ← à lire en premier
├── .checkpoints/      ← le cache par planche et par étape
└── perf.log
build/<Œuvre>/RAPPORT-SERIE.md   ← en mode --all
```

`RAPPORT.md` porte les sections qui comptent : planches à zéro bulle, détections faibles,
régions bi-lobées, **zones restaurées**, escalades de détection, et le pic mémoire pour un
webtoon.

Pour agréger plusieurs tomes en un tableau daté et comparable, voir
[banc-de-mesure.md](banc-de-mesure.md).

---

## Les clés de `config.yaml` qui changent le résultat

Tout vit sous `manga:`, qui **hérite** des sections racines par fusion profonde — n'y écrire
que ce qui doit différer.

### Détection — le premier levier

| Clé | Défaut | Effet |
|---|---|---|
| `manga.detection.conf_threshold` | `0.35` | seuil de confiance. Le baisser trouve plus de bulles **et plus de fausses** |
| `manga.detection.iou_threshold` | `0.45` | fusion des boîtes qui se recouvrent |
| `manga.detection.input_size` | `640` | résolution d'entrée du réseau. C'est le levier mesuré comme le plus efficace |
| `manga.detection.escalade.actif` | `true` | une planche pauvre en bulles est **repassée** à `input_size: 1024` et `conf_threshold: 0.20` |
| `manga.detection.scission.actif` | `true` | découpe une région bi-lobée en deux bulles |
| `manga.detection.fenetre_hauteur` | `2160` | hauteur d'une fenêtre de détection sur une planche très longue (webtoon) |
| `manga.detection.providers` | `[CPUExecutionProvider]` | mettre un provider GPU ici change le temps, pas le résultat |

### Nettoyage — l'invariant pixel-exact

| Clé | Défaut | Effet |
|---|---|---|
| `manga.nettoyage.mode` | `auto` | `auto` choisit entre remplir toute la bulle et n'effacer que le texte |
| `manga.nettoyage.seuil_uniformite` | `0.60` | en dessous, le fond de bulle est jugé trop texturé pour un aplat |
| `manga.nettoyage.seuil_abandon` | `0.35` | en dessous, la bulle **n'est pas repeinte du tout** — le dessin prime |
| `manga.nettoyage.seuil_texte` | `45` | ce qui compte comme encre |
| `manga.nettoyage.marge_bord` | `0.03` | marge intérieure conservée au bord de la bulle |

⚠ `manga/clean.py` a un **invariant pixel-exact testé** : une seule écriture,
`out_arr[paint] = style.background`, précédée de `paint = paint & region.mask`. Aucun pixel
hors masque de bulle n'est jamais touché. Ne pas contourner ce filet.

### Lettrage

| Clé | Défaut | Effet |
|---|---|---|
| `manga.typeset.font_path` | `''` | vide = la police du pack. La renseigner impose la tienne |
| `manga.typeset.taille_min` / `taille_max` | `11` / `60` | plage de corps de texte, en points |
| `manga.typeset.harmonisation` | `true` | rapproche les corps de texte d'une même planche |
| `manga.typeset.debordement` | `signaler` | un texte qui ne rentre pas est **signalé**, pas rogné en silence |
| `manga.typeset.majuscules` | `false` | tout en capitales, à la manière des comics |
| `manga.typeset.contour` | `auto` | contour du texte, pour la lisibilité sur fond chargé |

### Texte hors bulle (onomatopées) — livré en mode « rapport »

| Clé | Défaut | Effet |
|---|---|---|
| `manga.onomatopees.actif` | `true` | la passe tourne |
| `manga.onomatopees.mode` | `rapport` | **on détecte et on rapporte, on ne dessine pas.** Le seul mode que la mesure soutient aujourd'hui |
| `manga.onomatopees.vision` | `true` | joint l'image au modèle pour la lecture |
| `manga.onomatopees.effacement.mode` | `aucun` | l'effacement déterministe existe et est **désarmé** |

⚠ **La réserve porte un chiffre, et il est sévère.** Sur 60 zones hors bulle tirées au sort
(graine 21) et transcrites à l'œil, `manga-ocr` est exact **6 fois sur les 41** dont la lecture
nourrit le LLM — **14,6 %** — et « plausible mais faux » 21 fois. Il lit la narration imprimée
(4 sur 9) et presque jamais l'onomatopée stylisée (2 sur 14). Tout est dans
[`../mesures/sfx-2026-08-28.md`](../mesures/sfx-2026-08-28.md). C'est pourquoi le mode par
défaut ne dessine rien.

### Traduction et contexte

| Clé | Défaut | Effet |
|---|---|---|
| `manga.lot.planches` | `1` | planches par appel LLM. `--lot N` le surcharge en ligne de commande |
| `manga.contexte.planches_precedentes` | `3` | combien de planches de contexte le traducteur reçoit |
| `manga.mode_traduction` | `texte` | `texte` ou vision |
| `manga.langue_source` | `jp` | la langue des planches |
| `manga.terminologie.actif` | `true` | alimente `glossaire.yaml` depuis les planches |
| `manga.modeles.manga_relecteur` | *absent* | agent optionnel à mandat étroit, **non livré actif** |

### Sortie

| Clé | Défaut | Effet |
|---|---|---|
| `manga.rendu.formats` | `[cbz, images, psd]` | ce qui est produit |
| `manga.rendu.sens_lecture` | `droite_gauche` | numérotation des bulles **et** `ComicInfo.xml` |
| `manga.rendu.psd_original` | `true` | garde le scan d'origine en calque. ⚠ **`false` en webtoon** — sinon 420 Mo pour 9 bandes |
| `manga.formats.webtoon` | — | le bloc que `--format webtoon` applique : lecture gauche→droite, pas de calque d'origine |

---

## Quand ça ne marche pas

| Symptôme | Où regarder |
|---|---|
| Une planche ne rend aucune bulle | `python tools/apercu_detection.py … --resolutions --balayage`, puis `manga.detection.input_size` ; l'escalade est déjà censée l'attraper — `RAPPORT.md` § « Escalades de détection » dit si elle a tourné |
| Des bulles fantômes sur un webtoon | c'est la limite connue du format : **15 à 17 % de fausses détections**, contre 0 % sur le manga paginé. Le pipeline les repeint puis recolle le dessin ; `RAPPORT.md` les liste sous « Zones RESTAURÉES » |
| Une bulle repeinte en gris ou en noir | `manga.nettoyage.seuil_uniformite` et `seuil_abandon` — mais lire d'abord `RAPPORT.md`, le nettoyage a peut-être **refusé** de repeindre, ce qui est le bon comportement |
| Un texte déborde de sa bulle | `manga.typeset.taille_min`, `interligne_min`, `cesure_traits_union` ; `debordement: "signaler"` a déjà mis la planche au rapport |
| Un PSD manque | le format PSD plafonne à **30 000 px de côté**. La planche est refusée proprement et nommée sous « PSD REFUSÉ ». Découper la bande, ou retirer `"psd"` de `manga.rendu.formats` |
| Une onomatopée n'est pas traduite | c'est le comportement livré : `mode: "rapport"`. Voir la réserve chiffrée ci-dessus |
| Un pic mémoire sur webtoon | 637 Mo pour la détection, 1,4 à 1,7 Go avec la passe onomatopées. `RAPPORT.md` publie le chiffre |

Pour les drapeaux non listés ici, voir [`../COMMANDES.fr.md`](../COMMANDES.fr.md) § « Manga ».
