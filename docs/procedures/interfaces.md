# Procédure — les deux interfaces (`app.py`, `gui.py`)

Deux **façades**, pas une quatrième brique : elles n'ont aucun chemin de traitement propre.
Elles appellent les deux `process_volume` et `manga/edition.py`, et leur degré de confiance est
celui des briques qu'elles pilotent.

```powershell
python app.py      # console interactive (rich)
python gui.py      # interface graphique (PySide6) — planches, runs, édition directe
```

---

## 1. La console — `app.py`

Le même travail que les trois lignes de commande, avec les projets et les tomes listés à
l'écran, sans se rappeler des noms de dossiers. Rien de plus, rien de moins : ce qu'elle lance
est exactement ce que `run.py`, `run_manga.py` et `run_ocr.py` font.

À préférer quand on enchaîne plusieurs tomes ou qu'on ne se souvient plus du nom exact d'une
œuvre. `pip install -r requirements.txt` suffit.

## 2. L'interface graphique — `gui.py`

`pip install -r requirements-gui.txt` (PySide6).

C'est là qu'on **relit et corrige** une planche traduite : voir la pellicule du tome, ouvrir
une planche, corriger une réplique, déplacer une zone, relancer ce qui est périmé.

### Les gestes qui comptent

| Touche | Effet |
|---|---|
| `Ctrl+S` | enregistrer la planche affichée |
| `Ctrl+Maj+S` | **enregistrer les modifications du projet** — tout écrire, relettrer le périmé, réassembler une fois |
| double-clic sur une bulle | éditer sa réplique |
| `Entrée` dans la recherche | chercher dans **tout le tome** : répliques, corrections, OCR japonais |
| `Ctrl+Z` / `Ctrl+Y` | annuler / refaire |
| `Page préc.` / `Page suiv.` | planche précédente / suivante |
| `F` · molette · 🔒 | ajuster à la fenêtre · zoomer · garder le cadrage d'une planche à l'autre |
| `←↑→↓` | déplacer la zone sélectionnée d'un pixel (`Maj` : dix) |
| `Ctrl`+flèches | la retailler d'un pixel (`Ctrl+Maj` : dix) |
| `1`–`5` · `Échap` | choisir un outil de dessin · revenir à « Choisir » |
| `Ctrl+J` | afficher le journal |

⚠ **Tracer** une zone reste un geste de souris : le clavier déplace et retaille, il ne dessine
pas. L'écriture d'un déplacement part une demi-seconde après la dernière touche — un
retaillage réécrit `regions.json`, `masks.png` **et** la planche nettoyée.

### Lire la pellicule

| Pastille | Sens |
|---|---|
| `⟳` | rendu périmé |
| `✎n` | *n* répliques corrigées à la main |
| `↔n` | *n* textes déplacés |
| `⚠n` | *n* débordements |
| `∅` | aucune détection |
| `·` | jamais rendue |

Thème clair ou sombre : **Affichage → Thème**. Par défaut celui du système ; le canevas reste
sombre dans les deux, parce qu'on juge une planche sur fond neutre.

### Suivre un run — le bandeau (lot 32)

Dès qu'un run démarre, un bandeau apparaît **en pied de fenêtre** et y reste quelle que soit
la destination affichée : on peut retoucher une planche pendant qu'un tome tourne.

```
Manga · Mon Manga / Vol.2                      Traduction et rendu (5/6)
███████████████████░░░░░░░░░░  planche 84 / 131   ~1 h 10 restantes
page_0084.png · lot 80→99 · 3 planches par appel        [Arrêter proprement]
```

| Ce qui s'affiche | Ce que ça veut dire |
|---|---|
| `Traduction et rendu (5/6)` | la phase du run, et son rang. Un run manga en traverse six, un light novel trois |
| `planche 84 / 131` | l'avancement **compté**. Il ne recule jamais, même quand l'orchestrateur repasse par la planche 1 |
| `~1 h 10 restantes` | tiré du **débit observé** du run en cours, pas d'une constante. Absent tant qu'on ne sait pas |
| la ligne du bas | l'objet en cours : nom de fichier, plage de lot, numéro de bloc |
| une barre qui **balaie** au lieu de se remplir | on ne sait pas où on en est, et on le dit. Trois cas : le chargement du modèle de détection, un lot de traduction en vol, une image en cours de génération. Ni pourcentage ni temps restant ne les accompagnent |

⚠ **Aucun pourcentage n'est affiché, nulle part.** Ce n'est pas un oubli : la mesure du
2026-09-05 montre qu'une seule phase sur sept a un poids de temps utilisable, si bien que
« 64 % » se lirait comme 64 % du temps alors que la moitié des planches n'en coûte qu'un
tiers. Le compte, lui, porte son dénominateur
([progression-2026-09-05.md](../mesures/progression-2026-09-05.md)).

Le titre de la fenêtre porte le même compte en tête — `84/131 — Manga · … — Angelith` — pour
qu'on le lise dans la barre des tâches sans revenir à la fenêtre.

À la fin, le bandeau garde son bilan : « Terminé — 131 planches, 2 h 14, 3 avertissements »,
avec un bouton qui ouvre ces avertissements. **Aucune boîte de dialogue ne surgit** : un run
de nuit ne doit pas avaler la frappe de quelqu'un qui tape une réplique. Le journal
(`Ctrl+J`), lui, garde tout, dans l'ordre.

### Ce que le travail manuel garantit

Deux fichiers que le pipeline ne réécrit **jamais**, et qui survivent donc à un `--from` :

- `traduction_manuelle.json` — les répliques corrigées à la main ;
- `mise_en_page.json` — les blocs de texte déplacés.

Le travail non enregistré est recopié **toutes les 30 s** dans
`build/<Projet>/<Tome>/manga/.recuperation/`, et une reprise est proposée à la réouverture.
⚠ Ce dossier ne périme **aucun** rendu et n'est lu par aucune brique : un brouillon n'est pas
un enregistrement.

---

## Les clés de `config.yaml` qui changent le résultat

Le bloc `gui:` est **entièrement optionnel** : absent, les défauts de `gui/cache_apercu.py`
s'appliquent. **Aucune ligne de commande ne le lit.**

| Clé | Défaut | Effet |
|---|---|---|
| `gui.apercu.fenetre` | `10` | planches préchargées de part et d'autre de celle qu'on regarde. Composer un aperçu coûte **1,37 s en médiane** : les précharger est la seule façon de ne jamais attendre en tournant les pages. `10` = 21 planches en mémoire, ~21 Mo, ~27 s de fond. Monter la valeur précharge plus loin **mais retarde d'autant les planches proches** |
| `gui.apercu.plafond_mo` | `120` | plafond mémoire du cache d'aperçus, **en Mo et non en nombre d'entrées** — une planche à deux bulles et une à quatorze ne coûtent pas la même chose. Au-delà, les moins récemment vues sont oubliées et seront recomposées |

Tout le reste de ce que l'interface affiche vient des sections `manga:` et racines : pour
changer un lettrage ou un seuil de détection, c'est [manga.md](manga.md).

---

## La règle de couche, si tu touches au code

`gui/__init__.py` la pose : « toute logique métier vit dans `manga/`, en Python nu, et se teste
avec `pytest` sans que PySide6 soit installé. Ici on ne trouve que des fenêtres, des scènes et
des signaux. »

Elle est tenue : `pellicule.py`, `avancement.py`, `cache_apercu.py`, `modele_tome.py`,
`apercu.py` et `travailleur.progression_de_stage` sont sans Qt et testables directement.
**Tout ce qui décide se teste sans modèle et sans Qt.**

⚠ **Mise à jour 2026-09-05 (lot 32).** L'ÉTAT d'un run — phases, objet en cours, fraction
monotone — a quitté `gui/` pour `core/progression.py` : la console en a besoin autant que la
fenêtre. `progression_de_stage` l'a suivi, sans changer d'une ligne, et
`gui.travailleur.progression_de_stage` la ré-exporte ; elle était sans Qt mais enfermée dans
un module qui en importe, donc impossible à charger sans PySide6. Ce qui reste dans `gui/`
est ce qui décide de l'AFFICHAGE : `avancement.py` rend les lignes du bandeau de run, le
titre de fenêtre et le bilan de fin — toujours sans Qt.

⚠ Le compte de tests du dépôt a deux dénominateurs à cause de PySide6 : la CI mesure
**2 007 collectés avec, 1 879 sans**, soit **128 tests d'interface**. Ne pas confondre ces
chiffres avec le total toutes dépendances installées.

---

## Quand ça ne marche pas

| Symptôme | Où regarder |
|---|---|
| `gui.py` ne démarre pas | `pip install -r requirements-gui.txt` ; puis `python run_manga.py --check` |
| Tourner les pages est lent | `gui.apercu.fenetre` — mais la monter retarde les planches proches |
| L'application mange la mémoire | `gui.apercu.plafond_mo` |
| Une correction manuelle a disparu après un `--from` | elle n'a pas été enregistrée : seul `traduction_manuelle.json` survit, pas `.recuperation/` |
| Un rendu reste marqué `⟳` | `Ctrl+Maj+S` relettre le périmé et réassemble une fois |

Pour les raccourcis exhaustifs, voir [`../COMMANDES.fr.md`](../COMMANDES.fr.md) § « Interfaces ».
