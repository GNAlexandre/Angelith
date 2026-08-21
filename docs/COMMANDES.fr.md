# Angelith — mémo des commandes

Toutes les commandes, une ligne chacune. **Le *pourquoi* est dans le [README](README.fr.md)** ;
ici il n'y a que le *comment*.

Trois briques indépendantes, trois points d'entrée :

| Brique | Entrée | Ce qu'elle fait | Section README |
|---|---|---|---|
| **Light novel** | `run.py` | `.docx`/`.pdf`/`.epub`/`.md` → DOCX + EPUB + PDF traduits | §1 à §11 |
| **Manga** | `run_manga.py` | planches → bulles détectées, nettoyées, traduites, lettrées | §12 |
| **Scans** | `run_ocr.py` | pages japonaises en images → un `.md` que `run.py` lit | §13 |
| *(interfaces)* | `app.py`, `gui.py` | console interactive, interface graphique | §12 |

---

## Installation

```powershell
pip install -r requirements.txt              # socle + light novel
pip install -r requirements-manga.txt        # brique manga
pip install -r requirements-scan.txt         # brique scans (sous-ensemble de manga)
pip install -r requirements-gui.txt          # interface graphique (PySide6)
pip install -r requirements-dev.txt          # pytest
```

Hors pip : **Pandoc** (obligatoire pour le LN), **WeasyPrint** ou LaTeX (PDF), **Ollama**
lancé (`ollama serve`), et `unrar`/`unar` seulement pour lire des `.cbr`.

## Diagnostics

```powershell
python run.py --check                        # config, chemins, Pandoc, PDF, Ollama
python run_manga.py --check                  # + modèles ONNX et manga-ocr
python run_ocr.py --check                    # + cache du modèle d'OCR
python run.py --test-llm                     # juste la connexion au serveur LLM
```

Les trois `--check` relisent aussi **les clés de `config.yaml`** et signalent les fautes de
frappe (`font_paht` → « vouliez-vous dire `font_path` ? »). Ils **avertissent** sans refuser :
une clé inconnue est lue avec sa valeur par défaut, donc sans effet et sans message pendant
tout le run.

### Tests

```powershell
python -m pytest -q                                   # tout (1 657 tests)
python -m pytest -q -m "not modeles and not lent"     # sans la vision reelle (~52 tests de moins)
python -m pytest tests/test_manga_typeset.py -q       # un fichier
python -m pytest -q --durations=15                    # les 15 plus lents
```

| Marqueur | Ce qu'il exige | Mesuré |
|---|---|---|
| `modeles` | les poids sous `manga_models/` | vraie inférence ONNX |
| `lent` | rien, mais du temps | > 30 s |
| `llm` | un serveur LLM joignable | aucun test aujourd'hui |

⚠ Un marqueur ne cache **pas** un test qui pend : quand un fichier ne se terminait pas, la
cause était un vrai défaut (la passe `sfx` chargeait le détecteur de texte, 110 s par
planche). Ce qui reste marqué est ce qui est légitimement cher.

---

## Light novel — `run.py`

### Traduire

```powershell
python run.py "Mon LN" Vol.1                         # traduire (ou améliorer si FR présent)
python run.py "Mon LN" Vol.1 --dry-run               # toute la tuyauterie, sans appel LLM
python run.py "Mon LN" Vol.1 --force                 # refait les chapitres déjà faits
python run.py "Mon LN" Vol.1 --render-only           # régénère docx/epub/pdf depuis le .md
python run.py "Mon LN" --all                         # toute la série, tome après tome
```

### Reprendre, arrêter

```powershell
python run.py "Mon LN" Vol.1 --stop                  # dans un AUTRE terminal : arrêt propre
python run.py "Mon LN" Vol.1                         # relancer reprend au bloc suivant
```

`Ctrl+C` fait la même chose que `--stop`. L'unité d'arrêt est le bloc.

### Ne refaire qu'une étape

Étapes : `terminologie`, `traduction`, `correction`, `mise_en_page`, `rendu`.

```powershell
python run.py "Mon LN" Vol.1 --from correction       # correction → mise en page → rendu
python run.py "Mon LN" Vol.1 --chapitre 3            # refait le chapitre 3 en entier
python run.py "Mon LN" Vol.1 --chapitre 3 --from correction
```

### Glossaire

```powershell
python run.py "Mon LN" --optimize-glossary           # dédoublonne / fusionne / reclasse
python run.py "Mon LN" --extract-glossary            # relève les termes sans traduire
python run.py "Mon LN" --import-glossary fichier.docx
```

### Inspecter

```powershell
python run.py --list                                 # projets disponibles
python run.py "Mon LN" --list                        # tomes d'un projet
python run.py "Mon LN" Vol.1 --plan                  # découpage en chapitres, sans traduire
python run.py "Mon LN" Vol.1 --diff-stages           # ce que chaque agent apporte
python run.py "Mon LN" Vol.1 --verbose               # temps et tokens (aussi dans perf.log)
```

---

## Manga — `run_manga.py`

### Traduire

```powershell
python run_manga.py "Mon Manga" Vol.1                # tout le tome
python run_manga.py "Mon Manga" Vol.1 --dry-run      # détection et OCR réels, sans LLM
python run_manga.py "Mon Manga" Vol.1 --force        # refait TOUTES les étapes
python run_manga.py "Mon Manga" Vol.1 --lot 20       # 20 planches par appel LLM
python run_manga.py "Mon Manga" Vol.1 --lot 20 --think    # …avec raisonnement du traducteur
```

### Toute une œuvre en une commande (run de nuit)

```powershell
python run_manga.py "Mon Manga" --all                     # tous les chapitres restants
python run_manga.py "Mon Manga" --all --keep-awake --shutdown   # la nuit, puis extinction
python run_manga.py "Mon Manga" --all --stop              # arrêter la SÉRIE (autre terminal)
python run_manga.py "Mon Manga" --all --from rendu        # harmoniser toute l'œuvre, 0 appel LLM
```

Un chapitre **complet et à jour n'est même pas ouvert** (629 ms pour constater, contre
3 min 9 s pour rouvrir trois chapitres et réécrire leurs CBZ). Un chapitre qui échoue
**n'interrompt pas les suivants** ; une planche qui échoue n'interrompt pas son chapitre.

Au matin, deux fichiers :

| Fichier | Contenu |
|---|---|
| `build/<Œuvre>/RAPPORT-SERIE.md` | état de chaque chapitre, ce que le run a fait, ce qui reste |
| `build/<Œuvre>/perf.log` | journal de la série, suivable en direct (`Get-Content -Wait`) |

Code de sortie **1** si un chapitre a échoué, ou si un chapitre traité reste incomplet.

⚠ `--from rendu` et `--force` **annulent le saut** : sans ça, l'harmonisation de l'œuvre ne
toucherait aucun chapitre fini — c'est-à-dire exactement ceux qu'elle vise.

### Ne refaire qu'une étape, qu'une planche

Étapes : `detection`, `nettoyage`, `ocr`, `terminologie`, `traduction`, `sfx`, `rendu`.

```powershell
python run_manga.py "Mon Manga" Vol.1 --from rendu        # relettrer seulement
python run_manga.py "Mon Manga" Vol.1 --from traduction   # retraduire puis relettrer
python run_manga.py "Mon Manga" Vol.1 --from sfx          # le texte HORS bulle
python run_manga.py "Mon Manga" Vol.1 --page 3            # ne traiter que la planche 3
python run_manga.py "Mon Manga" Vol.1 --page 3 --from ocr
```

### Régler la détection sur une planche

```powershell
python run_manga.py "Mon Manga" Vol.1 --page 3 --from detection --conf 0.25 --iou 0.4
```

`--conf` et `--iou` **exigent `--page`** : un seuil pour tout le tome appartient à
`config.yaml > manga.detection`, où il laisse une trace.

### Glossaire

Le glossaire est le **même fichier** que celui du light novel
(`sources/<Œuvre>/glossaire.yaml`). Ces deux commandes ne touchent que lui : **aucune planche
n'est nettoyée, traduite, lettrée ni réassemblée**.

```powershell
python run_manga.py "Mon Manga" Vol.1 --extract-glossary   # relève les noms d'un chapitre
python run_manga.py "Mon Manga" --all --extract-glossary   # …de toute l'œuvre (run de nuit)
python run_manga.py "Mon Manga" --optimize-glossary        # dédoublonne / fusionne / reclasse
python run_manga.py "Mon Manga" Vol.1 --from rendu         # applique le résultat aux bulles
python tools/compter_variantes.py "Mon Manga" Vol.1        # combien de formes bannies subsistent
```

Un chapitre **sans OCR** est détecté et OCRisé à la volée ; un chapitre déjà traité ne repaie
rien (les relevés en cache sont re-fusionnés sans un appel). Sur un chapitre déjà **traduit**,
l'extraction remplit en plus les `interdits` à partir des variantes réellement produites —
c'est ce que `--from rendu` corrigera ensuite, sans un seul appel LLM.

Le dédoublonnage est lancé **une seule fois**, après le dernier chapitre, et seulement si le
glossaire a réellement bougé : l'agent glossariste travaille sur le glossaire entier de
l'œuvre, le rappeler par chapitre serait quinze appels pour un seul résultat.

| Option | Effet ici |
|---|---|
| `--page N` | ne relève que cette planche (les autres sont relues du cache, gratuitement) |
| `--force` | refait détection, OCR **et** relevé — après avoir modifié `prompts/terminologue.md` |
| `--from ocr` | refait l'OCR, donc le relevé ; `--from rendu` ne rappelle rien |
| `--dry-run` | détection/OCR réels, **glossaire non réécrit** (c'est une source, pas un build) |
| `--stop`, `Ctrl+C` | arrêt propre : le glossaire est sauvé, la relance reprend à la planche suivante |

Code de sortie **1** si un chapitre a échoué ; les autres sont quand même traités.

### Assembler, arrêter, inspecter

```powershell
python run_manga.py "Mon Manga" Vol.1 --assembler    # refait CBZ/PDF sans rien retraduire
python run_manga.py "Mon Manga" Vol.1 --stop         # arrêt propre (unité : la planche ou le lot)
python run_manga.py --list                           # œuvres manga
python run_manga.py "Mon Manga" --list               # état RÉEL de chaque chapitre
python run_manga.py --psd-test                       # vérifie l'export PSD
python run_manga.py "Mon Manga" Vol.1 --verbose      # + perf à l'écran (le perf.log, lui,
                                                    #   est écrit dans tous les cas)
```

`--list` sur une œuvre rend un verdict par chapitre, et non « le dossier de build existe » :

```
   · Chap.6   28 planche(s) à traiter        jamais traité
   ◐ Chap.9   12/28 planche(s)               interrompu, à reprendre
   ↻ Vol.4    1 planche(s) à relettrer       rendu en retard sur les données
   ✓ Vol.1    165 planche(s)                 complet et à jour → sauté par --all
   ⚠ Vol.2    aucune image ni archive        rien à traiter
```

---

## Scans japonais — `run_ocr.py`

Produit `sources/<Projet>/<Tome>/JAP/<Tome>.md`, que `run.py` lit ensuite **sans rien
changer**.

```powershell
python run_ocr.py "Mon LN" Vol.1                     # ~2 h pour 270 pages, reprenable
python run.py     "Mon LN" Vol.1                     # puis la traduction, inchangée
```

### Régler avant de payer deux heures

```powershell
python run_ocr.py "Mon LN" Vol.1 --page 100 --apercu       # image de contrôle, sans OCR
python run_ocr.py "Mon LN" Vol.1 --page 100 --apercu --seuil 96
python run_ocr.py "Mon LN" Vol.1 --page 100 --verbose      # la page, texte compris
```

### Reprendre, refaire, arrêter

Étapes : `analyse`, `lecture`.

```powershell
python run_ocr.py "Mon LN" Vol.1                     # reprend où le dernier run s'est arrêté
python run_ocr.py "Mon LN" Vol.1 --from lecture      # relit sans refaire l'analyse
python run_ocr.py "Mon LN" Vol.1 --force             # refait tout
python run_ocr.py "Mon LN" Vol.1 --langue JAP        # force le dossier de langue
python run_ocr.py "Mon LN" Vol.1 --stop              # arrêt propre (unité : la page)
python run_ocr.py "Mon LN" --all
```

À lire avant de traduire : `build/<Projet>/<Tome>/ocr/RAPPORT.md`, dont la première section
liste les pages douteuses.

---

## Runs de nuit (les trois briques)

```powershell
python run.py "Mon LN" Vol.1 --keep-awake --shutdown
python run_manga.py "Mon Manga" Vol.1 --keep-awake --shutdown
python run_ocr.py "Mon LN" Vol.1 --all --keep-awake --shutdown
python run.py "Mon LN" --all --keep-awake --shutdown-delay 300
```

`--shutdown` programme une extinction **annulable** ; `--shutdown-delay SECONDES` règle le
délai.

---

## Interfaces

```powershell
python app.py                                        # console interactive
python gui.py                                        # interface graphique (planches + runs)
```

### Raccourcis de l'interface graphique

| Touche | Effet |
|---|---|
| `Ctrl+S` | enregistrer la planche affichée |
| `Entrée` dans le champ de recherche | chercher dans **tout le tome** (répliques, corrections, OCR japonais) |
| `Ctrl+Maj+S` | **enregistrer les modifications du projet** (tout écrire, relettrer le périmé, réassembler une fois) |
| `Ctrl+Z` / `Ctrl+Y` | annuler / refaire |
| `Page préc.` / `Page suiv.` | planche précédente / suivante |
| `F` | ajuster la planche à la fenêtre |
| 🔒 (barre d'outils) | garder le cadrage d'une planche à l'autre |
| molette | zoomer |
| `Échap` | revenir à l'outil « Choisir » |
| double-clic sur une bulle | éditer sa réplique |
| `Ctrl+J` | afficher le journal |

Pastilles de la pellicule : `⟳` rendu périmé · `✎n` répliques corrigées à la main ·
`↔n` textes déplacés · `⚠n` débordements · `∅` aucune détection · `·` jamais rendue.

---

## Où va quoi

```
sources/<Projet>/<Tome>/JAP|ENG|ESP|FR/   sources light novel (+ le .md produit par run_ocr)
sources/<Projet>/<Tome>/manga/            planches ou archive .cbz/.cbr
sources/<Projet>/glossaire.yaml           glossaire de l'œuvre

build/<Projet>/<Tome>/                    sortie light novel + media/
build/<Projet>/<Tome>/manga/              pages_clean/, pages_out/, RAPPORT.md, le .cbz
build/<Projet>/<Tome>/ocr/                cache de l'OCR de scans + RAPPORT.md
```

Le travail non enregistré est recopié toutes les 30 s dans
`build/<Projet>/<Tome>/manga/.recuperation/`, et une reprise est proposée à la réouverture du
tome. ⚠ Ce dossier ne périme **aucun** rendu et n'est lu par aucune brique : un brouillon
n'est pas un enregistrement.

Fichiers que le pipeline ne réécrit **jamais**, et qui survivent donc à un `--from` :
`traduction_manuelle.json` (répliques corrigées à la main) et `mise_en_page.json` (blocs de
texte déplacés).
