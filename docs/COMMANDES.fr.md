# Angelith — mémo des commandes

Toutes les commandes, une ligne chacune. **Le *pourquoi* est dans le [README](README.fr.md)** ;
ici il n'y a que le *comment*.

> **Tu cherches le chemin normal plutôt que la liste exhaustive ?** →
> **[procedures/](procedures/README.md)** : une fiche courte par brique, avec les commandes
> dans l'ordre où on les lance **et les clés de `config.yaml` qui en changent le résultat**.
> Ce mémo-ci est exhaustif ; les fiches sont le trajet.

Quatre briques indépendantes, quatre points d'entrée :

| Brique | Entrée | Ce qu'elle fait | Section README |
|---|---|---|---|
| **Light novel** | `run.py` | `.docx`/`.pdf`/`.epub`/`.md` → DOCX + EPUB + PDF traduits | §1 à §11 |
| **Manga** | `run_manga.py` | planches → bulles détectées, nettoyées, traduites, lettrées | §12 |
| **Scans** | `run_ocr.py` | pages japonaises en images → un `.md` que `run.py` lit | §13 |
| **Illustration** | `run_illustration.py` | bible visuelle → images NEUVES, marquées, jamais dans l'œuvre | §12 |
| *(interfaces)* | `app.py`, `gui.py` | console interactive, interface graphique | §12 |

⚠ La quatrième est **expérimentale et désarmée** (`illustration.actif: false`). Elle ne modifie
aucune image existante et ne produit rien sans qu'un humain ait validé le prompt.

## Atelier d'illustration — `run_illustration.py`

```powershell
python run_illustration.py "Mon LN"            # L'ATELIER : il pose ses questions et génère
python run_illustration.py                     # idem, il demande d'abord l'œuvre
python run_illustration.py --check             # environnement, moteur, poids
python run_illustration.py --check --telecharger           # autorise le téléchargement (Go)
```

**Une seule commande suffit.** L'atelier demande **qui illustrer** — parmi les personnages de
l'œuvre, les mieux documentés d'abord — ou te laisse écrire toi-même la description que tu
veux. Puis le cadrage, le nombre d'images, **quelles images montrer au modèle** (une par une,
avec ce qu'on en sait), et enfin la validation : le prompt complet s'affiche, avec d'où vient
chaque mot, et répondre demande **ton nom**.

⚠ **Une ŒUVRE, pas un tome.** Les références d'un personnage vivent où l'éditeur les a mises —
sur le corpus de mesure, 7 des 10 références validées sont dans un autre volume que le
premier. La sortie va dans `build/<Projet>/illustrations/`. Nommer un tome **restreint la
lecture**, il ne change pas où l'on écrit :

```powershell
python run_illustration.py "Mon LN" Vol.2      # ne lit que le Vol.2
```

### Le chemin scripté, en deux phases

```powershell
python run_illustration.py "Mon LN" --phase prompt    # → build/<Projet>/illustrations/requete.yaml
#   … tu relis le fichier, tu corriges les prompts, tu écris ton nom dans validation.par,
#   … tu passes `valide` à true. C'est la PORTE : la phase image refuse tant qu'elle est fermée.
python run_illustration.py "Mon LN" --phase image     # bascule VRAM + génération

python run_illustration.py "Mon LN" --phase prompt --ecraser        # repart du squelette
python run_illustration.py "Mon LN" --phase prompt --personnage "Tory Noelle"
python run_illustration.py --rejouer build/…/tory.png.provenance.json     # rejeu + comparaison

# Surchargent illustration.prompt.* pour UN run, sans toucher à config.yaml
python run_illustration.py "Mon LN" --phase prompt --cadrage visage
python run_illustration.py "Mon LN" --phase prompt --forme categories
python run_illustration.py "Mon LN" --phase prompt --langue-prompt en

# Rendre la carte à ComfyUI — hors chemin nominal (illustration.vram.decharger_image: false)
python run_illustration.py --liberer-vram                    # une fois
python run_illustration.py --liberer-vram --repetitions 20   # le RELEVÉ du taux d'échec (lot 30)
```

⚠ **`--liberer-vram` appelle `POST /free`, qui fait segfauter ComfyUI environ une fois sur
sept** — relevé le 2026-08-29, et sept n'est pas un dénominateur. `--repetitions 20` est le
protocole que le `PLAN-30` L30.4 demande pour en obtenir un : il **sonde le serveur entre deux
appels**, parce que le mode d'échec est la mort du serveur et non une erreur HTTP. Il s'arrête au
premier serveur mort et dit à quel rang ; les dénominateurs s'additionnent d'une session à
l'autre. Il **n'arme rien** — la décision s'écrit à la main dans `config.yaml` — et il ne relance
jamais ComfyUI : Angelith ne pilote pas le cycle de vie d'un programme que tu as installé.

⚠ **N'interromps pas une génération.** Mesuré le 2026-08-30 : un `POST /interrupt` a coûté
**22 minutes** de réinitialisation de modèle au run suivant, et le cache d'exécution de
ComfyUI a resservi l'image *partiellement débruitée* du run avorté au graphe identique
suivant. Le moteur refuse désormais une génération rendue en moins de
`illustration.comfyui.plancher_secondes` (2 s) — mais mieux vaut laisser la file se vider.

### Ce que la phase 1 écrit, et comment on le relit (lot 26)

`requete.yaml` porte, **par personnage** :

| champ | ce qu'il dit | peux-tu le vider ? |
|---|---|---|
| `references` | les images d'IDENTITÉ, chacune avec son `motif` et son `retenue` | ❌ **non** — sans référence, la phase 2 retombe sur de la génération pure, et elle refuse |
| `ancrages_style` | les images de REGISTRE du tome, à préférer **sans visage** | ✅ oui |
| `attributs_sources` | d'où vient chaque mot du prompt : le fichier, la citation, l'origine | ✅ oui — c'est de la documentation |
| `graine` | `null` = aléatoire, un entier = reproductible | ✅ oui |
| `canaux` | les arguments TYPÉS du moteur (entités, image de contrôle) — livrés **désarmés** | ✅ oui |

⚠ **Chaque image porte son motif, retenue comme écartée.** Un utilisateur qui en retire une
doit voir pourquoi elle avait été prise ; sans motif, la porte humaine se réduit à un clic de
confiance. Décocher **toutes** les références d'un personnage qui en avait fait échouer la
phase 2 avec son motif, **avant** la bascule VRAM.

⚠ **Le prompt négatif porte le motif de chaque terme**, dans
`illustration/gabarits/portrait.yaml`. En retirer un est un choix, pas une faute — mais on ne
choisit pas de retirer ce dont on ignore la raison.

### Mesurer de quoi un prompt est fait (lot 26)

```powershell
# Étape 0 : le tableau des fragments, avec ses vides. Aucune image, aucun réseau.
python tools/banc_prompt.py "Mon LN" --fragments --markdown

# Étape 0.4 : les canaux structurés que TON serveur expose réellement (pas une page web)
python tools/banc_prompt.py "Mon LN" --canaux

# L26.0 : le choix des images. `--llm` ajoute la sélection par le modèle de VISION.
python tools/banc_prompt.py "Mon LN" Vol.1 --selection --llm

# Ceux-là GÉNÈRENT des images — moteur réel, plusieurs minutes par ligne de tableau
python tools/banc_prompt.py "Mon LN" Vol.1 --formes  --personnage "Tory Noelle"
python tools/banc_prompt.py "Mon LN" Vol.1 --langues --personnage "Tory Noelle"
python tools/banc_prompt.py "Mon LN" Vol.1 --style   --personnage "Tory Noelle"
```

⚠ **Le modèle de vision est DÉSARMÉ par défaut** (`illustration.prompt.llm.actif: false`).
Sans lui, la sélection est déterministe : reproductible sans serveur, donc testable en CI, et
elle ne coûte aucune seconde. Avec lui, elle coûte **un appel par image** — le lot le plus
petit possible, parce que `yume-27b` tient 32 768 jetons de contexte et que vingt
illustrations n'y entrent pas. Le coût est publié dans `RAPPORT.md`, face à celui de la
phase 2.

### Mesurer l'identité, la nouveauté et le style (lot 25)

```powershell
# Étape 0.2 : les cinq planchers du juge. AUCUNE image générée, aucun GPU — mais un
# encodeur ONNX, dont le chemin se donne ici ou par illustration.identite.encodeur.fichier.
python tools/banc_identite.py "Mon LN" Vol.1 --etalonnage --markdown `
  --encodeur illustration_models/dinov2-base.onnx

# Le juge lui-même : huit prétraitements mis en concurrence sur le corpus réel
python tools/banc_identite.py "Mon LN" Vol.1 --juge-variantes

# L25.1 : le balayage. Il GÉNÈRE — un paramètre à la fois, trois grandeurs par image
python tools/banc_identite.py "Mon LN" Vol.1 --balayage --personnage "Tory Noelle"

# Le matériel du juge HUMAIN : 20 triplets sans étiquette. Le banc ne rend aucun verdict.
python tools/banc_identite.py "Mon LN" Vol.1 --balayage --triplets 20 --markdown
```

⚠ **Les planchers sont propres à un corpus.** La médiane de confusion d'une œuvre ne dit rien
d'une autre : c'est pourquoi `illustration.identite.planchers.*` est livré à `null` et se
remplit depuis `--etalonnage`. Un plancher à `null` ne se prononce pas ; un plancher à `0` est
un seuil que rien ne franchit. Ce ne sont pas la même chose.

⚠ **Et la voie A est DÉSARMÉE par défaut** (`illustration.identite.actif: false`) : sur le
corpus de référence, le juge ne sépare « même personnage » de « personnages différents » que
**68 fois sur 100**. Tout est dans `docs/mesures/identite-2026-08-29.md`.

### Juger l'identité, pour de vrai (lot 29)

Le juge automatique du lot 25 ne sépare « même personnage » de « personnages différents » que
**68 fois sur 100**, et personne ne sait si 68 est un mauvais score — parce que personne n'a
mesuré ce qu'un **humain** fait sur les mêmes paires. Le protocole en aveugle n'est pas un
recours en cas d'échec de l'automatique : il en est l'**étalon**, et son produit est un
**accord**, pas un verdict.

#### D'abord le corpus, jamais la métrique

```powershell
python tools/bible.py "Mon LN" --corpus                  # le tableau 0 / 1 / 2 / ≥3
python tools/bible.py --tous --corpus --markdown         # tous les projets, publiable
python tools/bible.py "Mon LN" --revue --role identite   # couvertures en dernier, cadre proposé
```

⚠ **Deux comptes, et l'écart entre eux est le sujet.** Le premier prend toutes les références
d'identité validées, le second en **retire les couvertures**. Au lot 25, les trois références
validées du corpus étaient trois couvertures — dont deux le même dessin — et le seul compte de
gauche disait « corpus prêt ». La cible est **8 personnages, dont 4 à 3 références ou plus,
aucune couverture parmi elles**, et le tableau s'affiche **avant et après chaque revue**.

⚠ **Le rectangle est PROPOSÉ, pas décidé.** `--revue --role identite` propose un cadre par
cadrage (`visage` / `buste` / `pied`) et affiche le motif sur lequel il repose — « le haut de
l'encre est la tête ». Aucune détection de visage, aucun OpenCV : mesuré sur les 402
illustrations de `build/`, la boîte d'encre retire les **marges** (médiane 0,7747 de la page),
pas la page. C'est une assistance, pas une automatisation.

#### Puis le protocole en aveugle, et le seuil se fixe AVANT

```powershell
python tools/juge_humain.py "Mon LN" --paires 20 --seuil 14   # présente et enregistre
python tools/juge_humain.py "Mon LN" --paires 20              # relancé : REPREND
python tools/juge_humain.py "Mon LN" --rapport --markdown     # l'accord humain/automatique
```

⚠ **Il n'y a pas d'option `--seuil` à la lecture.** Le seuil est écrit dans `protocole.json` à
sa création et `--rapport` le lit **de là** : un seuil qu'on peut passer après avoir vu les
résultats ne mesure rien. Les réponses vont dans `reponses.jsonl`, horodatées, **en ajout
seul** — se reprendre ajoute une ligne, le journal garde les deux.

⚠ **N'ouvre pas `protocole.json` avant d'avoir répondu** : il porte la correspondance entre
A/B et les configurations. Les images présentées s'appellent `paire-07-A.png`, elles sont
écrites dans un ordre tiré au sort, et elles sont copiées **octet pour octet** — leur bloc
`tEXt` « générée par IA » voyage avec elles.

#### Et le coût, publié avant de lancer

```powershell
python tools/banc_identite.py "Mon LN" --devis                         # 8 × 10, la cible du plan
python tools/banc_identite.py "Mon LN" --devis --decors neutre,trame   # avec l'axe décor
```

Ce que le plan demande — 8 personnages × 10 images en **édition** — coûte **5 h 11 min** de
GPU. ⚠ Le dénominateur de ce chiffre vaut **1** : 233,7 s/image est un essai de sonde, pas la
médiane de quatre images qu'est 103,7 s en texte-vers-image. Et le devis **ne compte que le
GPU** : il ignore la demi-journée de relecture humaine, qui est le vrai poste dimensionnant.

#### L'axe « décor », fermé par défaut

```powershell
python tools/banc_identite.py "Mon LN" Vol.1 --balayage --personnage "…" `
  --decors neutre,trame,aucun --markdown
```

⚠ **Le défaut du dépôt ne bouge pas.** La part d'aplats de l'image générée vaut 0,6300 contre
0,3669 pour le tome, et « sur fond neutre » en est la cause probable — mais aucune mesure ne
désigne encore un remplaçant, et le dépôt ne change pas un prompt sur une hypothèse. Les
quatre variantes (`neutre`, `trame`, `sommaire`, `aucun`) existent pour que la mesure puisse
se faire ; un nom inconnu **lève**, avant tout chargement de poids, plutôt que de retomber en
silence sur `neutre`.

### Voir ce que le projet envoie à ComfyUI (lot 28)

Cinq sous-commandes, **aucune ne génère** : l'outil n'appelle que des routes en lecture. Générer
reste le travail de `run_illustration.py`, qui porte la porte humaine et le marquage ; un outil
capable d'envoyer un `/prompt` serait une seconde porte, non gardée.

```powershell
python tools/comfy.py --sonde        # version, variante, dossiers, nœuds tiers, VRAM, listes de modèles
python tools/comfy.py --valider      # les quatre graphes du dépôt + celui de config.yaml
python tools/comfy.py --valider illustration/workflows/qwen-image-edit-2511.api.json
python tools/comfy.py --graphe build/Mon_LN/illustrations/requete.yaml    # le graphe SUBSTITUÉ, écrit
python tools/comfy.py --graphe … --sortie C:\tmp\graphes                 # ailleurs qu'à côté
python tools/comfy.py --diff a.api.json b.api.json                       # champ par champ
python tools/comfy.py --journal      # le dernier run : temps, VRAM, lignes du serveur archivées
python tools/comfy.py --journal --projet "Mon LN"
```

**`--valider` fait six contrôles sans dépenser une seconde de GPU** : le fichier est-il au format
API ; chaque `class_type` existe-t-il sur le serveur ; chaque fichier de modèle nommé est-il dans la
liste que le nœud expose ; quels canaux le graphe déclare **et lesquels il exige** ; les pas et le
guidage sont-ils compatibles avec sa LoRA ; et **où atterrit la copie que ComfyUI écrit en plus de
celle qu'Angelith marque**. Le code de sortie vaut 1 sur un refus, donc il se scripte. Chaque refus
porte sa correction.

⚠ **La sixième (lot 30) ne refuse presque jamais.** Sur un `SaveImage` — le cas de tous les
graphes du dépôt — elle pose une **réserve** qui nomme la copie non marquée du dossier `output/`
de ComfyUI et dit comment la réduire (`PreviewImage`, qui écrit dans `temp/` : ComfyUI la vide à
son redémarrage, et ce client la récupère sans changer une ligne). Elle **refuse**
`SaveImageWebsocket`, que ce client ne sait mécaniquement pas lire — il récupère l'image par
`/history` puis `/view`, et ce nœud ne publie rien dans l'historique.

⚠ **Un graphe CANDIDAT n'échoue pas.** Depuis le lot 30, le dépôt livre
`qwen-image-edit-2511-controle.api.json`, qui n'a jamais tourné et dont le poids n'est installé
nulle part. Il porte un bloc `_candidat` : ses « nœud absent » et « modèle absent » sont
rétrogradés en **réserves**, affichées avec le motif, la source du poids et sa licence. Sans quoi
`--valider` sans argument passerait en rouge sur toute machine du monde.

⚠ **La cinquième est la seule dont l'échec ne produit aucun message côté ComfyUI** : `guidage: 4.0`
avec une LoRA Lightning s'exécute très bien et rend une image **brûlée**.

⚠ **Serveur éteint : les contrôles 2 et 3 sont NON FAITS, pas passés**, et l'outil l'écrit avec ces
mots. Les contrôles 1, 4 et 5 marchent hors ligne.

⚠ **`--graphe` n'envoie rien et ne téléverse rien.** Le nom sous lequel ComfyUI connaîtra chaque
image de référence est calculé depuis l'empreinte de son contenu : le JSON produit est donc
exactement celui qui partirait. Glisse-le dans ComfyUI — il est au format API — et tu rejoues à la
main, graine comprise, ce que le projet a fait tourner.

**`run_illustration.py --check` fait tourner cette validation** depuis la 2.22.0, et refuse
**avant** le déchargement du LLM : la VRAM libre y est comparée au pic mesuré (14 417 Mio le
2026-08-29 sur le graphe Lightning), en comptant au crédit ce que PyTorch a déjà réservé — sans
quoi le contrôle mentirait à chaque seconde génération.

**Chaque image produite garde son graphe à côté d'elle** : `<image>.png.graphe.json`, plus les trois
lignes de journal du serveur (`loaded completely` / `loaded partially`, `lowvram patches: N`,
`Prompt executed in …`) dans son sidecar de provenance. C'est la différence entre une trace et un
souvenir : sans elles, un run qui a produit une image étrange ne laissait aucun moyen de savoir si
le transformeur avait été rogné — donc si l'image vient du régime mesuré ou de l'autre, à 64,3 s/pas.

### Rendre la VRAM après un run

Le modèle d'image reste chargé : **12 083 Mio** occupés après un run (mesuré le 2026-08-29 sur
RX 7900 XT). Un `run.py` ou un `run_manga.py` lancé derrière trouve la carte prise.

```powershell
# Rend la carte : mesuré 12 083 Mio → ~470 Mio en quelques secondes
Invoke-RestMethod -Uri http://127.0.0.1:8188/free -Method Post `
  -ContentType 'application/json' `
  -Body '{"unload_models": true, "free_memory": true}'
```

⚠ **N'utilise pas `curl.exe` pour celle-ci sous PowerShell 5.1** : quelle que soit la façon
d'échapper le corps JSON, PowerShell le mange avant que curl ne le voie, et ComfyUI répond
`HTTP 500` sur un `json.loads` qui échoue. Vérifié dans les deux formes le 2026-08-29.
`curl` fonctionne normalement depuis `bash` ou `cmd`.

Angelith sait le faire tout seul en fin de run — `illustration.vram.decharger_image` — mais
**la clé est DÉSARMÉE par défaut** : sur sept appels à `/free`, **un a fait segfauter ComfyUI**
(violation d'accès dans son propre `model_management.py`, ROCm 7.14). Les images sont écrites
et marquées avant cet appel, donc un plantage ne coûte qu'un redémarrage de ComfyUI — mais
c'est une surprise qu'on n'impose pas par défaut.

⚠ Fermer ComfyUI rend évidemment la carte aussi, et sans ce risque.

⚠ `--phase` n'est **pas** `--from` : aucune étape n'est invalidée en amont, et le dossier
`illustrations/` n'entre pas dans le graphe des checkpoints. Le supprimer ne relance rien.

### L'atelier graphique, et la galerie (lot 27)

```powershell
python gui.py            # destination « Illustrations », dans la nav latérale (2.25.0)
```

La destination a **deux pages**, et on ne va de la première à la seconde qu'en passant par la
phase 1 : le **catalogue** (qui est illustrable, cadrage, nombre d'images, graine, galerie de
ce qui a été produit), puis **l'écran de relecture du prompt** — le cœur du lot. Il montre le
prompt éditable avec son original restaurable, le prompt négatif avec le motif de chaque
terme, les vignettes en **deux groupes** (identité / style) chacune avec son motif, et la
source de chaque attribut. « Valider et générer » demande **ton nom**.

⚠ **Il n'y a pas de « générer directement »** : ni bouton, ni raccourci, ni clé de
configuration, pas même pour rejouer une requête déjà validée. Le rejeu passe par `--rejouer`.

⚠ **Un run par lot.** L'atelier annonce la fourchette mesurée avant d'engager le GPU, et sa
barre reste indéterminée jusqu'à la première image terminée : le coût varie d'un facteur 14,7
sur la carte de référence (103,7 s à 1 524 s), une barre qui annoncerait un pourcentage se
tromperait d'un facteur dix un jour sur deux.

```powershell
# La galerie en ligne de commande — l'équivalent des boutons de la destination
python run_illustration.py "Mon LN" --inventaire    # combien, dans quel état, quel poids
python run_illustration.py "Mon LN" --garder build/Mon_LN/illustrations/aya.png
python run_illustration.py "Mon LN" --jeter  build/Mon_LN/illustrations/rate.png
python run_illustration.py "Mon LN" --purger        # supprime les REJETÉES, sur confirmation
```

⚠ **Garder DÉPLACE**, vers `sources/<Projet>/illustrations/`, qui survit à un `rm -r build/` —
que ce dépôt recommande lui-même après un MAJEUR. Une image produite en 103,7 s de GPU **n'est
pas régénérable** : la même graine sur une autre révision de modèle ne rend pas la même image.

⚠ **Jeter ne supprime pas** : un rejet est une donnée dont la mesure d'identité a besoin. La
purge est un geste séparé, et elle annonce ce qu'elle va détruire.

⚠ **Une image produite ne peut pas devenir une référence.** Garder l'inscrit dans
`bible.yaml` sous `images_generees[]`, une clé distincte de `references[]`. Reboucler une
sortie dans l'entrée ferait dériver le personnage à chaque tour, et la dérive est invisible
image par image.

### Insérer les illustrations dans les sorties du light novel (lot 27)

```yaml
# config.yaml
illustration:
  inserer_dans_sorties: true          # false par défaut : un tome relancé sort ISO-OCTET
  insertion:
    position: "debut_chapitre"        # | "fin_chapitre" | "tete_de_volume"
```

Armée, `python run.py "Mon LN" Vol.1` insère les images **retenues** dans le Markdown
assemblé, au début du premier chapitre qui **nomme le personnage** — le nom vient du sidecar
de provenance, pas d'une devinette. `RAPPORT.md` liste chaque image insérée, avec son
personnage et sa graine.

⚠ **La légende n'a pas d'interrupteur** : « Illustration générée par IA — ne fait pas partie
de l'œuvre originale », sous chaque image, dans les trois formats. Aucune clé ne la vide ;
`core/insertion.py` lève sur une légende vide. Son texte vient du **pack de langue cible**,
donc un tome anglais porte la version anglaise.

⚠ Cette clé ne concerne **que le light novel**. La brique manga rend des planches, et rien n'y
est composité — c'est la frontière de `illustration/frontiere.py`, et ce lot n'y touche pas.

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
python -m pytest -q                                   # tout (5 034 tests au 2026-09-06)
python -m pytest -q -m "not modeles and not lent"     # la boucle courte : 4 855 (57 de moins)
python -m pytest tests/test_manga_typeset.py -q       # un fichier
python -m pytest -q --durations=15                    # les 15 plus lents
```

**Couverture** — la commande exacte du job `tests` de la CI, rejouable telle quelle :

```powershell
pip install -r requirements-dev.txt                    # pytest-cov
python -m pytest -m "not lent and not modeles" -q --cov --cov-report=xml:coverage.xml
```

La cible est `source =` de [`.coveragerc`](../.coveragerc) : six paquets, pas les cinq
scripts racine. `coverage.xml` est lu par SonarQube Cloud, jamais commité (`.gitignore`).

⚠ La CI produit **deux** rapports, pas un : le job `banc` refait la même mesure sur ce que
le premier exclut (`-m "modeles"`, la vraie inférence ONNX). Un seul rapport publierait une
couverture sans la détection de bulles ni l'OCR en se présentant comme celle du projet.

```powershell
python -m pytest tests/test_banc_corpus_synthetique.py -m "modeles" -q --cov --cov-report=xml:coverage-banc.xml
```

| Marqueur | Ce qu'il exige | Mesuré |
|---|---|---|
| `modeles` | les poids sous `manga_models/` | vraie inférence ONNX |
| `lent` | rien, mais du temps | > 30 s |
| `llm` | un serveur LLM joignable | aucun test aujourd'hui |

⚠ Un marqueur ne cache **pas** un test qui pend : quand un fichier ne se terminait pas, la
cause était un vrai défaut (la passe `sfx` chargeait le détecteur de texte, 110 s par
planche). Ce qui reste marqué est ce qui est légitimement cher.

#### La police japonaise des tests

`tests/conftest.py` fabrique sa planche synthétique avec une police japonaise **du système**.
Elle est résolue par [`tools/polices.py`](../tools/polices.py) : d'abord la variable
`ANGELITH_POLICE_JP`, puis une liste de candidats par plateforme.

```powershell
$env:ANGELITH_POLICE_JP = "C:\Windows\Fonts\meiryo.ttc"   # pointer une police précise
```

```bash
sudo apt-get install -y fonts-noto-cjk                    # Linux : le candidat de la CI
```

⚠ **Sans police, `tests/test_fixture_police.py` ÉCHOUE — il ne skippe pas.** C'était le vrai
défaut que le lot 20 corrige : l'ancien `pytest.skip` faisait disparaître toute la couverture
détection / OCR / orchestrateur **en silence**, ce qui interdisait toute CI sur un autre OS
que Windows. Un test rouge est une information ; un skip vert n'en est pas une.

### Les garde-fous de dépôt (lot 20)

Tous rejouables en local, avant le push — c'est le but : un garde-fou qu'on ne peut vérifier
qu'en poussant se découvre faux au moment où il refuse à tort une PR pressée.

```powershell
# Le compte de tests, et sa comparaison entre deux systèmes
python tools/compte_de_tests.py
python tools/compte_de_tests.py -m "not lent and not modeles" --sortie compte.json

# Le MÊME compte, sans PySide6 — sans desinstaller quoi que ce soit (lot 31)
python -m pytest --collect-only -q -p tools.compte_sans_pyside

# La disclosure IA des commits de la branche (CONTRIBUTING.md)
python tools/verifier_disclosure.py --base origin/main
python tools/verifier_disclosure.py --historique 100        # le taux sur l'historique

# Ni poids de modele, ni corpus, ni titre d'oeuvre dans le diff
python tools/verifier_arbre.py --diff origin/main
python tools/verifier_arbre.py --index                      # avant un push vers le miroir
python tools/verifier_arbre.py --suivi --non-bloquant       # l'etat de l'arbre entier

# CHANGELOG, version, prompts, tableau date
python tools/verifier_livraison.py --base origin/main

# Les notes de version d'un tag, decoupees dans le CHANGELOG
python tools/notes_de_version.py 2.11.0 --verifier
```

### Le découpage des bandes très allongées (lot 31)

```powershell
# Les fenetres de detection d'une bande — sans effet sur une planche paginee,
# qui n'est jamais decoupee. Defauts : 2160 px de hauteur, 900 px de recouvrement.
python run_manga.py "Mon Webtoon" Chap.11 --format webtoon --fenetre-hauteur 3000
python run_manga.py "Mon Webtoon" Chap.11 --format webtoon --fenetre-recouvrement 1200
```

⚠ Le recouvrement doit rester **≥ la plus haute bulle attendue** — mesurée à **833 px** sur le
corpus — sinon une bulle peut être coupée par toutes les coutures qui la traversent, et le
rejet des détections coupées la perd alors pour de bon. `manga/detection.py` rabote de toute
façon au-delà de 80 % de la hauteur de fenêtre : un recouvrement de 2 159 px sur 2 160
produirait **7 841 fenêtres** pour une seule bande.

Les deux options sont aussi dans l'interface, destination **Webtoon**, groupe « Découpage de la
bande » — et nulle part ailleurs : elles sont inertes sur une planche paginée. Le **sens de
lecture**, lui, y est affiché mais pas modifiable : le changer sur un tome déjà détecté ferait
reprendre toutes ses planches à la détection.

### Ce que coûte le lancement de l'interface (lot 31)

```powershell
# Le tableau du demarrage : temps avant le premier pixel, fichiers lus, apercus, memoire
python tools/mesure_demarrage.py --attente 10 --markdown

# Le meme releve sur un autre corpus — celui d'un cas degrade, par exemple
python tools/mesure_demarrage.py --attente 10 --racine <racine> --markdown
```

L'outil enveloppe les méthodes de `Fenetre` **de l'extérieur** et dit « n'existe plus » plutôt
que d'échouer : c'est ce qui lui permet de tourner des deux côtés d'une refonte, et donc de
produire une colonne « avant » et une colonne « après » comparables
([coquille-2026-09-04.md](mesures/coquille-2026-09-04.md)).

### Ce que chaque drapeau de CLI devient dans l'interface (lot 33)

```powershell
# Le tableau complet : 93 arguments des quatre CLI, croises avec gui/parametres.py
python tools/inventaire_drapeaux.py

# Les quatre nombres seulement — formulaire / ailleurs / non expose / non classe
python tools/inventaire_drapeaux.py --resume

# Ce qui n'est classe nulle part, ET les motifs devenus orphelins
python tools/inventaire_drapeaux.py --manquants
```

Il lit les quatre CLI avec `ast` et **resout `cli.ajouter_flags_veille`** : les trois drapeaux
de veille ne sont ecrits dans aucune des trois CLI qui les portent, et c'est exactement ce
qu'un `grep add_argument` ne voit pas. `tests/test_inventaire_drapeaux.py` echoue si un
drapeau neuf apparait sans etre classe — ou si un motif survit au drapeau qu'il justifiait.

### Ce que l'endpoint LLM sait dire de ses modeles (lot 33)

```powershell
python -c "import core.modeles as m; c=m.lister('http://localhost:11434/v1'); print(c.phrase()); [print(x.ligne()) for x in c.modeles]"
```

Un GET, rien d'autre : aucun telechargement, aucune generation, aucune ecriture dans
`config.yaml`. Ce que la sonde ne sait pas dire — la capacite vision hors Ollama, la fenetre
de contexte reellement servie — s'affiche « inconnu »
([lanceurs-2026-09-05.md](mesures/lanceurs-2026-09-05.md) §3).

### Ce que le canal de progression dit pendant un run (lot 32)

```powershell
# Rejouer les trois traces de reference : reculs, denominateurs, secondes sans temps restant
python tools/tracer_progression.py --markdown --rejouer --analyser tests/corpus/progression/*.jsonl

# Reconstruire la trace d'un run deja passe, depuis son perf.log
python tools/tracer_progression.py --markdown --anonyme --depuis-perf build/*/*/manga/perf.log

# Enregistrer un run REEL sous un Reporter decorateur (couteux : le run tourne vraiment)
python tools/tracer_progression.py --enregistrer "Mon Manga" Vol.1 --brique manga --sortie t.jsonl

# Le poids de chaque phase, mesure sur les perf.log de build/
python tools/banc_progression.py --markdown
python tools/banc_progression.py --detail --anonyme     # une ligne par run
```

Le second refuse tout poids dont l'écart min-max dépasse un **facteur 3** — au 2026-09-05, une
phase sur sept passe la règle, et c'est pourquoi l'interface n'affiche **aucun pourcentage** :
elle affiche un compte, qui porte son dénominateur
([progression-2026-09-05.md](mesures/progression-2026-09-05.md)).

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
python run.py "Mon LN" --migrate-glossary ancien.yaml   # réintègre un glossaire ANTÉRIEUR
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
# Voir ce que donnerait une relance — sans rien écrire
python tools/apercu_detection.py "Mon Manga" Vol.1 --page 3 --balayage

# …y compris en balayant les RÉSOLUTIONS d'entrée (⚠ une inférence par résolution)
python tools/apercu_detection.py "Mon Manga" Vol.1 --page 3 --resolutions --balayage

# Appliquer
python run_manga.py "Mon Manga" Vol.1 --page 3 --from detection --conf 0.25 --iou 0.4
```

`--conf` et `--iou` **exigent `--page`** : un seuil pour tout le tome appartient à
`config.yaml > manga.detection`, où il laisse une trace. Dans les deux cas l'**arbitre**
tranche (`manga/detection_retry.py`) : baisser un seuil fait toujours apparaître des régions, la
question est lesquelles, et le doute profite à la détection en place — elle a déjà été payée en
OCR et en traduction.

`input_size` n'a délibérément **pas** d'équivalent en ligne de commande : sa place est la
config, où elle vaut pour le tome entier et se retrouve au run suivant. Une résolution appliquée
à une seule planche produirait un tome hétérogène dont rien ne garderait la trace.

### La planche qui ne rend aucune bulle

Depuis la 2.4.0, une planche qui rend **zéro bulle alors qu'elle porte de l'encre** reçoit
automatiquement une **seconde inférence** à une résolution plus élevée, et l'arbitre décide si
le résultat remplace le premier. Il n'y a rien à faire : c'est le comportement livré.

```powershell
# Ce que l'escalade a donné sur le tome : RAPPORT.md, section « Escalades de détection »
# Le décompte avant/après sur tous les volumes de build/
python tools/banc.py --tous --markdown
```

Pour la désarmer — par exemple sur un tome dont les pages blanches sont nombreuses et dont on
connaît déjà le résultat :

```yaml
manga:
  detection:
    escalade:
      actif: false          # rend exactement le comportement d'avant la 2.4.0
```

⚠ Elle coûte **une inférence de plus sur les planches suspectes seulement**, et n'invalide
aucun cache : une planche déjà détectée reste sautée comme avant.

### Le webtoon (bandes verticales)

```powershell
python run_manga.py "Mon Webtoon" Chap.11 --format webtoon
```

Le format attend les images sous `sources/<Œuvre>/<Chapitre>/webtoon/<LANGUE>/1.png`, `2.png`…
Il est reconnu tout seul par ce chemin ; `--format webtoon` le force quand la source est à
plat.

Ce que le format change, et rien d'autre : le **sens de lecture** passe en gauche→droite (pour
la numérotation des bulles envoyée au modèle **et** pour `ComicInfo.xml`), et le PSD perd son
calque de scan d'origine — un chapitre de 9 bandes pèse **420 Mo** de PSD sinon. Tout le reste
est hérité du manga, y compris le découpage des bandes en fenêtres de détection, qui n'est pas
un réglage de format mais une conséquence de la géométrie de la planche.

**Ce qu'il faut savoir avant de lancer**, mesuré sur les 9 bandes du chapitre de référence
(`docs/mesures/webtoon-2026-08-26.md`) :

- une bande de 1080×10 000 est détectée en **8 fenêtres**, soit ~7 s au lieu de ~0,9 s ;
- le pic de mémoire monte à **637 Mo** pour la détection, **1,4 à 1,7 Go** si la passe
  onomatopées tourne. `RAPPORT.md` publie désormais ce chiffre ;
- **une détection sur six ou sept est fausse** (15 à 17 %, contre 0 % sur le manga paginé). Le
  pipeline les repeint puis recolle le dessin d'origine, et `RAPPORT.md` les liste sous
  « Zones RESTAURÉES ». C'est la limite connue du format, pas une panne.

Pour voir ce que le réseau perçoit d'une bande donnée, sans rien écrire :

```powershell
python tools/apercu_detection.py "Mon Webtoon" Chap.11 --page 3 --resolutions --balayage
```

La ligne « la planche occupe N px du canevas » est celle qui compte : en dessous du seuil, la
bande est découpée en fenêtres ; au-dessus, une seule passe suffit.

⚠ Si un PSD manque à l'appel : le format PSD plafonne à **30 000 px de côté**. Au-delà, la
planche est refusée proprement — le reste de ses sorties est écrit normalement — et
`RAPPORT.md` la nomme sous « PSD REFUSÉ ». Découpe la bande en amont, ou retire `"psd"` de
`manga.rendu.formats`.

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

### Mesurer — le banc

Les instruments de mesure lisent **uniquement** les caches sous `build/` : aucun modèle
chargé, rien de réécrit, et ils se lancent pendant qu'un run tourne. `--corpus` est la seule
exception (mesurer un rappel demande de détecter).

```powershell
python tools/banc.py --tous                          # tous les volumes de build/, en un tableau
python tools/banc.py "Mon Manga" Vol.2               # un seul volume
python tools/banc.py --tous --markdown > docs/mesures/banc-2026-08-25.md   # daté, commit + config
python tools/banc.py --tous --traduction             # le banc de traduction, sans appel LLM
python tools/banc.py --tous --json                   # pour tracer une courbe
python tools/banc.py --corpus tests/corpus/synthetique --markdown   # rappel / precision / F1
python tools/corpus_synthetique.py                   # (re)genere le corpus annote
python tools/mesurer_bulles.py "Mon Manga" Vol.1     # distribution du remplissage
python tools/mesurer_structure.py --tous             # types de bulle, groupes, locuteurs
python tools/mesurer_structure.py --tous --profils   # + les centiles bruts, pour refixer un seuil
python tools/verifier_ordre.py "Mon Webtoon" --all   # ordre de lecture persiste
```

#### Le banc du TEXTE HORS BULLE (lot 21)

Le seul qui mesure ce qui est écrit **à côté** des bulles : triage, distribution des aires,
**uniformité du fond local** (la mesure qui décide de ce qu'un effacement pourra faire),
polarité de l'encre, remplissage, orientation.

```powershell
python tools/banc_sfx.py --tous                      # les 2 456 zones des 6 tomes, en un tableau
python tools/banc_sfx.py --tous --markdown           # + date, commit, empreinte de config
python tools/banc_sfx.py --tous --sans-pixels        # aires et triage seuls, sans ouvrir les planches
python tools/banc_sfx.py --tous --json zones.json    # une entrée par zone, pour tracer
python tools/banc_sfx.py --tous --echantillon 60     # la vérité terrain, graine 21 (reproductible)
python tools/banc_sfx.py --tous --echantillon 60 --crops D:/crops   # + les images
```

⚠ **`--crops` écrit des planches sous droit d'auteur** : viser un dossier **hors du dépôt**.
C'est pour cela que le chemin n'a pas de valeur par défaut.

⚠ Les pixels sont lus dans `pages_out/`, qui est bit-à-bit la planche d'origine **hors des
bulles** (invariant testé de `clean.py`). Sur un tome rendu en mode `"glose"`, ce n'est plus
vrai — la glose est dessinée à côté de la zone : pointer alors les planches d'origine avec
`--source <dossier>`.

Ce que ce banc a donné au lot 21 : [`sfx-2026-08-28.md`](mesures/sfx-2026-08-28.md).

#### Le banc de l'EFFACEMENT (lot 22)

Il ne dit pas ce qu'une zone **est** — c'est le banc précédent — mais ce qu'un effacement
déterministe en **ferait**. Trois mesures, à lire ensemble : l'**empreinte** (part de la boîte
repeinte : le coût), le **résidu** (ce qu'il reste du glyphe : l'efficacité) et la **couture
rapportée au grain** du fond intact (1,0 = se raccorde comme le fond se raccorde à lui-même :
la visibilité).

```powershell
python tools/banc_effacement.py --tous --markdown          # les deux tableaux, par palier
python tools/banc_effacement.py --tous --texte-seul        # les seules zones classées « texte »
python tools/banc_effacement.py --tous --json zones.json   # une entrée par zone
python tools/banc_effacement.py --tous --dilatation 1.6    # un point du balayage
python tools/banc_effacement.py --tous --seuil-uniformite 0  # « tout uniforme », pour comparer
python tools/banc_effacement.py --tous --images D:/avant-apres          # les vrais avant/après
python tools/banc_effacement.py --tous --synthetique fig.png            # la figure publiable
```

⚠ **`--images` écrit des planches sous droit d'auteur** : viser un dossier **hors du dépôt**,
comme `--crops` ci-dessus. `--synthetique`, lui, fabrique trois fonds de toutes pièces et peut
donc être publié — c'est la figure de `docs/img/effacement-2026-08-28.png`.

⚠ **Ce banc ignore délibérément le garde-fou de lecture, et le pipeline non.**
`manga/effacement.py` refuse d'effacer une zone dont la lecture n'est pas concordante, et ce
taux vaut 0 % sur le corpus : un banc qui respecterait la règle mesurerait zéro zone. Les deux
questions sont distinctes — « le déterministe suffit-il ? » et « a-t-on le droit de s'en servir
ici ? » — et doivent le rester.

Ce que ce banc a donné au lot 22 : [`relettrage-2026-08-28.md`](mesures/relettrage-2026-08-28.md).

### Comparer un détecteur CANDIDAT au détecteur en place (lot 16)

Celui-ci charge des modèles — c'est la seconde exception à la règle ci-dessus, et elle est
assumée : mesurer un détecteur qui n'a jamais tourné sur le corpus demande de le faire tourner.
Il n'écrit toujours **rien** sous `build/`.

```powershell
# Rappel / precision / F1, tous les detecteurs a la meme resolution
python tools/banc_candidats.py --corpus tests/corpus/synthetique --actuel `
    --yolo poids/ogkalu_bubble.onnx --rtdetr poids/detector.onnx --input-size 640

# Les planches a ZERO bulle des dix volumes — le regime de l'escalade
python tools/banc_candidats.py --tous --sur-zero --actuel --yolo poids/ogkalu_bubble.onnx `
    --ocr --texte --markdown > docs/mesures/detecteurs-candidats-2026-08-26.md

# Un webtoon, avec l'OCR du projet
python tools/banc_candidats.py "Mon Webtoon" Chap.11 --actuel --rtdetr poids/detector.onnx --ocr
```

| Option | Effet |
|---|---|
| `--actuel` | mesurer aussi le détecteur du dépôt, tel que `config.yaml` le construit |
| `--yolo` / `--rtdetr` | un export ONNX candidat — répétable ; d'où les poids viennent est dans [`manga_models/README.md`](../manga_models/README.md) |
| `--input-size` | la résolution **commune** : c'est le « à armes égales » du lot 16 |
| `--sur-zero` | ne mesurer que les planches que le cache rend à zéro bulle |
| `--ocr` | lire les bulles trouvées — coûteux, et sans valeur sur du japonais (cf. ci-dessous) |
| `--texte` | interroger le détecteur de TEXTE sur chaque bulle — coûteux, et le seul indicateur valable là où `manga-ocr` hallucine |

⚠ **`--ocr` ne dit rien sur un tome japonais.** `manga-ocr` est un modèle génératif : il rend
rarement une chaîne vide, même sur du dessin. C'est pour cela que `--texte` existe. Sur une
source latine (`rapidocr`), `--ocr` reste l'indicateur le plus proche des « zones restaurées ».

| Option | Effet |
|---|---|
| `--build DOSSIER` | mesurer une **copie** d'un cache sans toucher à `config.yaml` — `build/` reste en lecture seule |
| `--sans-encre` | ne pas ouvrir les planches : plus rapide, colonne « dont encrées » laissée vide |
| `--markdown` | ajoute l'en-tête de publication (date, commit, version, sha256 de `config.yaml`) |

⚠ **Les bulles se comptent depuis `regions.json`, pas depuis `qa.json`** : une planche sans
contrôle qualité a quand même des bulles, et le banc la signale dans une colonne `sans qa` au
lieu de la soustraire. Le détail est dans
[chiffres-de-reference.md](chiffres-de-reference.md), le protocole dans
[banc-de-mesure.md](procedures/banc-de-mesure.md).

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
| `←` `↑` `→` `↓` | déplacer la zone sélectionnée d'un pixel (`Maj` : dix) |
| `Ctrl`+flèches | la retailler d'un pixel (`Ctrl+Maj` : dix) |
| `1`–`5` | choisir un outil de dessin |

⚠ **Tracer** une zone reste un geste de souris : le clavier déplace et retaille, il ne dessine
pas. L'écriture d'un déplacement au clavier part une demi-seconde après la dernière touche —
un retaillage réécrit `regions.json`, `masks.png` **et** la planche nettoyée.

Thème clair ou sombre : « Affichage → Thème ». Par défaut, celui du système ; le canevas reste
sombre dans les deux.

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


## Compiler — le gel et l'installeur

⚠ **Windows seulement**, et le motif est écrit dans `docs/mesures/empaquetage-2026-09-06.md` §9 :
aucun `.spec` n'a jamais été exercé sur un runner Linux, et Inno Setup n'y existe pas.

```powershell
# 1. l'environnement du paquet LIVRÉ — le jeu complet, manga-ocr compris
pip install -r requirements.txt -r requirements-gui.txt -r requirements-manga.txt
pip install pyinstaller          # ⚠ PAS une dépendance du projet : un empaqueteur n'est pas
                                 #   une dépendance de ce qu'il empaquette

# 2. tout le reste — UNE commande
python tools/geler.py
```

C'est tout. `tools/geler.py` régénère `installeur/version.iss` depuis `core/version.py`, gèle en
**un dossier** (`--workpath .pyinstaller`, jamais `build/`, qui porte les tomes traduits),
rejoue les **trois vérifications** du gel, construit l'installeur et écrit
`dist/SHA256SUMS.txt`.

⚠ **MISE À JOUR 2026-09-06, lot 38 : cette section listait CINQ commandes à recopier dans le
bon ordre.** Une séquence qu'on recopie est une séquence qu'on finit par exécuter à moitié — le
lot 37 s'est lui-même livré avec un installeur portant le numéro de la version précédente, faute
d'avoir régénéré `installeur/version.iss` avant de compiler. Et `ci.yml` cherchait Inno Setup
dans `C:\Program Files (x86)` uniquement, alors qu'une installation par `winget --scope user`
le met dans `%LOCALAPPDATA%\Programs` : le job aurait marché, la commande documentée non. **La
CI appelle désormais le même outil**, ce qui rend les deux chemins identiques par construction.

### Les variantes

```powershell
python tools/geler.py --outils              # dit ce qui manque, et ne fait rien
python tools/geler.py --sans-installeur     # le gel et ses trois vérifications
python tools/geler.py --verifier-seulement  # rejoue les 3 tests sur un dist/ existant
```

### Les trois vérifications, et pourquoi elles existent

Un artefact non testé est un artefact qu'on livre cassé une fois sur trois. Le gel a trois
pannes classiques, et **les trois ont été rencontrées pour de vrai** pendant le lot 37 :

| # | Ce qui est vérifié | La panne qu'elle attrape |
|---|---|---|
| 1 | `--version` rend celle de `core/version.py` | la version perdue au gel |
| 2 | le diagnostic structuré se collecte | un chemin resté relatif à `__file__` |
| 3 | la fenêtre s'ouvre sur l'accueil, sans tome | un module Qt élagué de trop |

⚠ Elles tournent sur **`angelith-console.exe`**, pas sur `angelith-gui.exe` : sous Windows, un
binaire lié en sous-système « fenêtre » n'a pas de sortie standard. Le premier essai de ces
vérifications n'a rien écrit et n'est jamais sorti.


### Publier — ce qu'un tag déclenche, et ce que l'application ira chercher (lot 40)

Poser un tag `vX.Y.Z` déclenche **deux** workflows, qui écrivent sur la **même** release :

| Workflow | Runner | Ce qu'il y met |
|---|---|---|
| `publication.yml` | `ubuntu-latest` | le **corps** — la section de CHANGELOG découpée par `tools/notes_de_version.py` |
| `ci.yml`, job `artefact` | `windows-latest` | les **fichiers** — `dist/*.exe` et `dist/SHA256SUMS.txt`, plus le même corps |

⚠ **Les deux écrivent le corps, avec le même générateur.** `tools/notes_de_version.py` sur le
même CHANGELOG produit le même texte à l'octet près : l'ordre d'arrivée des deux workflows est
donc sans conséquence, par construction plutôt que par espoir. Laisser l'un des deux muet
reviendrait à parier sur ce qu'une action tierce fait d'une release existante dont on ne lui
donne pas le corps.

⚠ **Les deux sont nécessaires, et c'est le second qui manquait.** Jusqu'au lot 40, la release
ne portait **aucun fichier** : le job `artefact` téléversait des artefacts de *workflow*, qui
n'en sont pas. « Aide › Rechercher une mise à jour… » n'aurait donc rien eu à télécharger.

⚠ **`SHA256SUMS.txt` part avec l'exécutable, et sans lui rien ne s'installe.** C'est ce fichier
que `core/maj.py` lit pour vérifier ce qu'il vient de télécharger ; sans certificat de
signature, c'est la seule garantie d'intégrité offerte — et elle ne vaut que si le fichier est
publié. Une release qui porterait l'installeur sans lui ferait ouvrir la page des releases au
lieu de proposer l'installation : un installeur qu'on ne peut pas vérifier vaut moins qu'un
lien, parce qu'il aurait l'air vérifié.

⚠ **Ce que cette empreinte ne fait pas** : elle détecte un téléchargement tronqué ou altéré en
transit. Elle ne remplace **pas** une signature de code — aucun certificat ne signe ces
binaires, et le fichier d'empreintes vient de la même release, donc de la même main. C'est
écrit à l'écran dans la fenêtre de mise à jour, pas seulement ici.

**Couper la vérification** : `config.yaml > maj.verifier: false`. Elle est **armée** depuis la
2.34.0 ; la case « Ne plus afficher » de la fenêtre, elle, ne masque que la **fenêtre** et se
décoche depuis Préférences › Au démarrage.

**Où va quoi dans une installation gelée** — c'est `core/installation.py` qui décide, et rien
de tout cela ne change quand on lance `python gui.py` depuis le dépôt :

| Quoi | Où | Écrit ? |
|---|---|---|
| l'application, `config.yaml` livré, `langues/`, `templates/` | le dossier d'installation | jamais |
| le `config.yaml` modifiable, `.angelith/`, les poids téléchargés | `%LOCALAPPDATA%\Angelith` | oui |
| `sources/` et `build/` — les œuvres | `Documents\Angelith` | oui |

Les trois se déplacent par `ANGELITH_DONNEES`, `ANGELITH_DOCUMENTS` et `ANGELITH_REGLAGES`.
`--config <chemin>` l'emporte toujours sur la résolution automatique.
