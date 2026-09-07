# Procédure — scans japonais (`run_ocr.py`)

Transformer un light novel japonais livré **en images de pages** en un Markdown que la brique
light novel lit ensuite sans rien changer.

> **Cette brique est en BÊTA**, et la réserve est nommée : l'analyse de mise en page est
> mesurée sur **un seul tirage** et ses seuils, quoique tous relatifs et non absolus, n'ont pas
> encore vu d'autre imprimeur. La lecture elle-même est celle de `manga-ocr`, déjà éprouvée.

---

## 1. Poser les pages

```
sources/<Projet>/<Tome>/JAP/001.png, 002.png…
```

Sortie : `sources/<Projet>/<Tome>/JAP/<Tome>.md` — c'est-à-dire **une source pour `run.py`**,
posée exactement là où il l'attend. Les illustrations rencontrées en chemin partent dans
`JAP/media/` avec un marqueur d'image que le pipeline sait réinsérer.

## 2. Régler AVANT de payer deux heures

C'est le geste qui définit cette brique. Un tome de 270 pages coûte environ **deux heures** ;
l'aperçu coûte deux secondes et n'écrit rien d'autre qu'une image de contrôle.

```powershell
python run_ocr.py --check                                   # manga-ocr, poids, environnement
python run_ocr.py "Mon LN" Vol.1 --page 100 --apercu        # image de contrôle, AUCUN OCR
python run_ocr.py "Mon LN" Vol.1 --page 100 --apercu --seuil 96
python run_ocr.py "Mon LN" Vol.1 --page 100 --verbose       # la page seule, texte compris
```

Sur l'aperçu, on regarde **la grille de colonnes**. Si elle est régulière et qu'elle en compte
autant que la page, le seuil est bon. Si la page sort en une seule bande, il est mauvais.

⚠ **L'écart entre le bon seuil et le mauvais n'est pas un compromis, c'est une falaise.**
Mesuré sur cinq pages du Vol.1 du tirage de référence : à **112** la page sort en 16 colonnes
régulières ; à **128** elle sort en **une seule bande** — le halo JPEG a refermé toutes les
gouttières.

## 3. Lire

```powershell
python run_ocr.py "Mon LN" Vol.1                    # ~2 h pour 270 pages, reprenable
python run_ocr.py "Mon LN" --all
python run_ocr.py "Mon LN" Vol.1 --all --keep-awake --shutdown
```

Deux étapes : **`analyse` → `lecture`**.

```powershell
python run_ocr.py "Mon LN" Vol.1 --from lecture     # relit sans refaire l'analyse de page
python run_ocr.py "Mon LN" Vol.1 --force            # refait tout, cache ignoré
python run_ocr.py "Mon LN" Vol.1 --langue JAP       # force le dossier de langue
python run_ocr.py "Mon LN" Vol.1 --stop             # arrêt propre (unité : la page)
```

## 4. Relire le rapport, puis traduire

```powershell
# À LIRE avant de lancer la traduction : la première section liste les pages douteuses.
build/<Projet>/<Tome>/ocr/RAPPORT.md

python run.py "Mon LN" Vol.1                        # la traduction, inchangée
```

---

## Les clés de `config.yaml` qui changent le résultat

Tout vit sous `scan:`, qui **hérite** des sections racines par fusion profonde.

| Clé | Défaut | Effet |
|---|---|---|
| `scan.seuil_encre` | `null` | binarisation. `null` = **choisi par balayage**, page par page, en gardant le seuil qui révèle la grille de colonnes la plus régulière. ⚠ Ne fixer une valeur qu'après avoir regardé un aperçu |
| `scan.caracteres_par_tranche` | `10` | **la constante critique de toute la brique** — voir ci-dessous |
| `scan.lot_ocr` | `16` | imagettes par appel au modèle. Mesuré : 0,655 s/tranche une par une, **0,488 s/tranche par lots de 16**, pour une sortie identique au caractère près |
| `scan.ruby` | `ignorer` | furigana. `parentheses` rend `唖然(あぜん)` — utile pour relever les lectures de noms propres, mais la position insérée est **estimée** et peut glisser d'un caractère |
| `scan.illustration_encre_max` | `0.12` | au-delà de cette part d'encre, la page n'est pas du texte : c'est une illustration. Elle part dans `media/` avec un marqueur |
| `scan.titre_pas_min` | `1.6` | une page dont les glyphes sont au moins 1,6× le corps du tome, tenant en 3 colonnes ou moins, est une page de **titre** : elle sort en `# …`, ce qui suffit à faire une frontière de chapitre |
| `scan.colonnes_min` | `4` | en dessous, la page n'a pas de grille exploitable |
| `scan.ocr.hors_ligne` | `auto` | comme `manga.ocr.hors_ligne` |

### Pourquoi `caracteres_par_tranche` est la clé qui compte

`manga-ocr` **redimensionne son entrée en 224 × 224**. Une colonne japonaise entière de
40 caractères en ressort donc **inventée** : 23 à 29 caractères rendus, sans rapport avec la
page. Découpée en tranches de 8 à 16 caractères, la même colonne est lue à **~95 %**.

- **Monter** cette valeur ramène l'hallucination.
- **Baisser** cette valeur multiplie les coutures entre tranches.

`10` est le compromis mesuré. Ce n'est pas un réglage de performance, c'est ce qui sépare une
lecture d'une invention.

---

## Quand ça ne marche pas

| Symptôme | Où regarder |
|---|---|
| Le texte est du charabia plausible | `scan.caracteres_par_tranche` — c'est la signature de l'hallucination par redimensionnement |
| L'aperçu montre une seule bande au lieu de colonnes | `scan.seuil_encre` : balayer par `--apercu --seuil N` jusqu'à retrouver la grille |
| Une page de texte est partie dans `media/` | `scan.illustration_encre_max` est trop bas pour ce tirage |
| Aucun chapitre détecté ensuite par `run.py` | les pages de titre n'ont pas été reconnues : `scan.titre_pas_min`, puis `decoupage.chapter_patterns` côté light novel |
| Le run est trop lent | `scan.lot_ocr`, et vérifier que le provider d'exécution est celui qu'on croit (`--check`) |

**Toujours lire `build/<Projet>/<Tome>/ocr/RAPPORT.md`** : sa première section liste les pages
douteuses, et c'est ce qu'on relit à la main avant de dépenser la traduction.

Pour les drapeaux non listés ici, voir [`../COMMANDES.fr.md`](../COMMANDES.fr.md) §
« Scans japonais ».
