# Angelith — pipeline de fan-traduction multi-sources (local, multi-agents)

Chaîne **100 % locale** pour traduire des light novels : elle lit des **Tomes entiers**
(`.docx` / `.pdf` / `.epub`), **synthétise** une ou plusieurs fantrads (JP / EN / ES / ZH) en
français — ou **améliore** un brouillon FR existant —, **détecte automatiquement
chapitres et sous-chapitres**, **récupère et réintègre les images**, applique ta
**mise en page**, et exporte un **Markdown complet** + **Word / EPUB / PDF**.

Conçu pour **Ollama** sur ta 7900XT, sans coût de token.

---

> **Tu cherches une commande ?** → **[COMMANDES.md](COMMANDES.fr.md)** : toutes les commandes
> des trois briques, une ligne chacune. Ce README-ci explique le *pourquoi* ; le mémo donne
> le *comment*.
>
> **Tu veux juste lancer une brique ?** → **[procedures/](procedures/README.md)** : une fiche
> courte par brique — les commandes dans l'ordre, les clés de `config.yaml` qui comptent, et
> « quand ça ne marche pas ».
>
> **Tu cherches un chiffre ?** → **[mesures/](mesures/README.md)** : les comptes rendus datés,
> un par lot livré, chacun avec son commit et son dénominateur.

## Sommaire

1. [Structure des sources](#1-structure-des-sources)
2. [Une source → trois formats](#2-une-source--trois-formats-et-tes-styles-exacts)
3. [Orchestrateur & modèle](#3-orchestrateur--modèle)
4. [Le pipeline, étape par étape](#4-le-pipeline-étape-par-étape)
5. [Détection des chapitres et sous-chapitres (Parties)](#5-détection-des-chapitres-et-sous-chapitres-parties)
6. [Images](#6-images)
7. [Prérequis](#7-prérequis)
8. [Utilisation — toutes les commandes](#8-utilisation--toutes-les-commandes)
9. [Personnalisation](#9-personnalisation)
10. [Limites (honnêtes)](#10-limites-honnêtes)
11. [Arborescence](#11-arborescence)
12. [Manga (brique indépendante)](#12-manga-brique-indépendante)
13. [Sources en images — OCR d'un LN japonais scanné](#13-sources-en-images--ocr-dun-ln-japonais-scanné)

---

## 1. Structure des sources

Un dossier par projet, un sous-dossier par Tome, puis un sous-dossier par langue :

```
sources/
└── Mon LN/
    └── Vol.1/
        ├── ENG/        ← Tome complet en .docx, .pdf ou .epub (référence de sens principale)
        ├── JAP/        ← VO (facultatif) — référence de sens absolue ; un .epub acheté convient
        ├── ESP/        ← .pdf (souvent « print-to-PDF », plusieurs fichiers possibles)
        ├── CHINOIS/    ← idem
        └── FR/         ← brouillon à AMÉLIORER (facultatif)
```

- Tu peux ne mettre **qu'un** dossier (ex. juste `ENG/`) : projet simple, traduction depuis l'anglais.
  `langues.sources_utilisees` (config.yaml) te permet aussi de **limiter** les langues réellement
  utilisées même quand plusieurs sont présentes — de 1 seule à toutes.
- Plusieurs fichiers dans un dossier sont **concaténés dans l'ordre de lecture** : prologue
  d'abord, chapitres/parties triés **numériquement** (`Part.2` avant `Part.10`), épilogue et
  postface en dernier (détectés par mots-clés FR/EN/JP). Vérifie l'ordre avec `--plan`. Pour une
  source éclatée en nombreux PDF (ex. un chapitre = plusieurs `Chap.N Part.M.pdf`), c'est ce qui
  garantit que le texte reconstitué est dans le bon ordre avant l'alignement avec les autres langues.
- **Si `FR/` existe → mode AMÉLIORATION** : le brouillon FR devient la base, les autres langues
  servent à corriger le sens. Sinon → mode TRADUCTION (synthèse).

---

## 2. Une source → trois formats (et tes styles exacts)

On génère un **Markdown canonique balisé** ; Pandoc le rend dans les trois formats depuis cette source unique. **Ton `templates/reference.docx` est ton propre fichier de styles** : la sortie Word reprend donc *exactement* « Corps de texte », « Pensée » et « Paragraphe de liste » — avec ton **tiret cadratin automatique** (généré par le style, pas écrit dans le texte) et l'**italique automatique** des pensées.

```
Markdown ──┬─► .docx  (reference.docx → tes styles Word, tiret « — » auto)
canonique  ├─► .epub  (epub.css → classes .dialogue / .pensee ; tiret via CSS ::before)
           └─► .pdf   (weasyprint, même CSS que l'EPUB → rendu cohérent)
```

Chaque bloc porte une **classe** (EPUB/PDF) et un **custom-style** (Word). Réglage dans
`config.yaml > rendu.styles` et `rendu.dialogue_dash_in_text` (laissé à `false` puisque ton
style « Paragraphe de liste » ajoute déjà le tiret — sinon le rendu affiche un double tiret « — — »).

**Filet de sécurité contre les styles Word hallucinés.** Un agent peut écrire un
`custom-style="…"` qui ressemble à un style Word (ex. le nom d'affichage français
« Corps de texte ») sans correspondre au nom **interne** réel du style dans
`reference.docx` (ex. `Body Text`) — Pandoc crée alors un `styleId` en double,
corrompant la définition de style dans le `.docx` de sortie. Avant chaque rendu, tout
`custom-style` qui ne correspond à aucun style connu de `reference.docx` est
**neutralisé** (converti en texte simple) plutôt que transmis tel quel à Pandoc.

---

## 3. Orchestrateur & modèle

**Orchestrateur sur mesure, sans framework** (pas de CrewAI/LangGraph) : du Python qui
parle à **Ollama** via l'API compatible OpenAI (`http://localhost:11434/v1`). Le serveur
est interchangeable : n'importe quel backend compatible OpenAI marche en changeant
`llm.base_url`.

**Modèle (reco juin 2026, 20 Go) :** comme on travaille **par blocs**, la fenêtre de
contexte n'est plus un facteur limitant en soi ; vise un **MoE rapide ~24-30B**
(ex. **Gemma 4 26B-A4B** ou **Qwen 3.5**). Le mode « thinking » est **activé sur le
traducteur** (l'agent central) et le terminologue via l'endpoint `reflexion`, et laissé
désactivé ailleurs (`llm.think: false` global) — le raisonnement aide à tenir le contexte et
la terminologie mais reste lent, donc réservé. Avec Ollama, ce réglage se fait **par requête** : pas
besoin de charger le modèle en double, on peut l'activer pour certains agents seulement
(cf. §9). Mets l'identifiant exact du modèle (celui affiché par `ollama ls`) dans
`config.yaml > modeles` (vérifie-le avec `python run.py --test-llm`).

---

## 4. Le pipeline, étape par étape

| Étape | Niveau | Rôle |
|------|--------|------|
| Terminologue | bloc | Voit le glossaire **catégorisé** déjà construit (personnages/lieux/organisations/créatures/objets/termes/événements) et l'enrichit/corrige à chaque bloc — pas de doublons, décisions cohérentes d'un bloc au suivant. |
| *(Glossariste)* | chapitre | **Automatique** juste après la terminologie de chaque chapitre : dédoublonne, fusionne les variantes et reclasse le glossaire — avant que les agents suivants ne s'en servent. |
| Traducteur-synthétiseur (**central, thinking**) | bloc | Recoupe les sources (ou améliore le brouillon FR) ; produit un **français limpide** (reformulation pilotée par `naturalisation.intensite`), applique les **temps du récit** et la **terminologie stricte** ; marque `<!-- AMBIGU: … -->` les doutes. |
| Correcteur | bloc | **Relit** la sortie du traducteur et **corrige les fautes** restantes (temps du récit, terminologie/formes interdites, genres, anglicismes, guillemets) — sans reformuler le style. |
| *(Images)* | chapitre | Ancre les illustrations à leur position (amélioration) ou les réinjecte proportionnellement (traduction). |
| Mise en page | bloc | Classe (narration / dialogue / pensée / encadré), drop-cap, émet le Markdown canonique. |
| *(Traductions forcées)* | bloc | Remplacement déterministe des entrées `force: true` du glossaire, **juste après la traduction** — garanti, indépendant de ce que le modèle a produit ; les étages suivants voient donc déjà la terminologie canonique. |

Les étapes *(en italique)* sont des passes **déterministes ou automatiques**, pas des agents LLM à part entière (sauf le glossariste, qui est un agent mais tourne sans intervention). Le **Chapitre** reste l'unique unité d'orchestration : chaque agent d'écriture traite un chapitre **entier** (tous ses blocs — et donc toutes ses éventuelles Parties, cf. section 5) avant que l'agent suivant ne prenne le relais. Le découpage en blocs est **déterministe** (par paragraphes, borné par `decoupage.max_block_chars`) et exécuté **avant** les agents. Les sources de référence sont découpées **proportionnellement au volume de texte** de chaque bloc du pivot, pour rester réellement alignées sur lui (et non par simple nombre de paragraphes, qui décalait la référence dès que les paragraphes n'étaient pas homogènes).

**Alignement des chapitres de référence.** Un même nombre de chapitres ne garantit pas un alignement 1:1 : il suffit qu'une frontière soit mal placée d'un côté pour décaler le contenu. Le pipeline compare donc la taille de chaque chapitre de référence à sa part attendue (sa proportion dans le pivot) et **recale les frontières** manifestement dérivées, en redistribuant le texte entre chapitres voisins. Sans ça, le traducteur reçoit du texte hors-chapitre et le traduit **en double**. Tout recalage est signalé dans `RAPPORT.md` et dans `perf.log`.

**Garde-fous par bloc, communs aux 4 agents d'écriture.** Un bloc vide, emballé (sort largement
plus que sa taille attendue), qui a perdu trop de mots par rapport à son entrée
(`config.yaml > garde_fous.perte_mots_ratio`), ou qui a perdu un **titre de Partie** (`##`,
cf. section 5) présent en entrée, déclenche un **retry automatique à température réduite**
avant de renoncer ; en dernier recours, le bloc retombe sur sa version précédente.
`RAPPORT.md` résume ces issues (voir plus bas).

**Redécoupage-relance (traduction).** Quand la cause de l'échec est la **taille du bloc** —
budget « thinking » épuisé (le modèle raisonne et ne produit jamais de réponse finale),
sortie qui sature le plafond, troncature — le bloc est **coupé en deux et chaque moitié est
relancée**, avec son propre plafond de sortie et ses références réalignées, au lieu d'être
abandonné et réinjecté en langue source. Réglé par `garde_fous.redecoupage_*` (section 9).

Sorties dans `build/<projet>/<tome>/` : `<projet>_<tome>.md` (le **Markdown complet** à
manipuler), `chapters/chNN.md`, `media/`, les exports, et `RAPPORT.md` — **résumé chiffré**
(durée, blocs ok/vides/emballés/perte de mots/titre perdu, retries, appels LLM et vitesse
moyenne) suivi du détail par chapitre (Parties détectées, points AMBIGU,
propositions de glossaire). Les checkpoints par bloc (`.checkpoints/`) sont **conservés**
après le rendu — voir `--from` en section 8 pour relancer une seule étape.

---

## 5. Détection des chapitres et sous-chapitres (Parties)

### 5.1 Cascade de signaux

La détection combine plusieurs signaux complémentaires, du plus fiable au plus coûteux
(mode `decoupage.detection: "auto"`, par défaut) :

```
┌─ 1. Nom de fichier ───────────────────────────────────────────────┐
│    "… Chap.3 Part.2.pdf", "… Prologue.pdf", "… Epilogue.pdf"      │
│    → regroupe déjà les parties d'un même chapitre par nom de      │
│      fichier, avant même de lire le contenu.                     │
└─────────────────────────────────────────────────────────────────┬─┘
                                                                    │
┌─ 2. Contenu — signaux STRUCTURELS combinés (par langue) ─────────▼─┐
│    • styles de titre Word natifs   (Heading/Titre 1-2 → # / ##)   │
│    • mots-clés                     (chapter_patterns, ancrés en   │
│                                      début de ligne — jamais en    │
│                                      pleine phrase)                │
│    • police + gras COMBINÉS        (jusqu'à 2 paliers : le plus   │
│                                      grand = Chapitre, l'autre =   │
│                                      Partie) — couvre les PDF sans │
│                                      style et les .docx où les     │
│                                      titres sont tapés à la main   │
└─────────────────────────────────────────────────────────────────┬─┘
                                                                    │
┌─ 3. Repli LLM ────────────────────────────────────────────────────▼─┐
│    "auto" : seulement si 1+2 ont trouvé MOINS DE 2 chapitres.       │
│    "llm"  : le modèle traite TOUTES les sources (plus lent, sans   │
│             effet en --dry-run).                                   │
└──────────────────────────────────────────────────────────────────┘
```

### 5.2 Hiérarchie à 2 niveaux : Chapitre → Partie (jamais l'inverse)

Une **Partie** (sous-chapitre) est toujours **imbriquée dans un Chapitre** — le
découpage ne connaît que ces deux niveaux. Cas réel (`sources/roman C/Vol.1/ENG`, un
PDF sans aucun style de titre, où les titres sont des entrées de journal datées) :

```
Chapitre 3 — "Year 1938, Summer 1"        ← palier de police le plus grand (24.7pt, gras)
 ├─ Partie 3.1 — "April 1st, Evening"      ← palier suivant (17.2pt, gras)
 ├─ Partie 3.2 — "April 1st, Night"
 └─ Partie 3.3 — "April 2nd, Morning"
Chapitre 4 — "Year 1938, Summer 2"
 ├─ Partie 4.1 — "April 17th, Evening"
 └─ Partie 4.2 — "April 17th, Night"
```

`python run.py "roman C" Vol.1 --plan` affiche exactement cette hiérarchie, en
sous-lignes numérotées sous chaque chapitre :

```
[en] 10 chapitre(s) détecté(s) :
    3. Year 1938, Summer 1
         3.1  April 1st, Evening
         3.2  April 1st, Night
         3.3  April 2nd, Morning
    4. Year 1938, Summer 2
         4.1  April 17th, Evening
         4.2  April 17th, Night
```

**Rétrocompatibilité garantie** : un projet dont les sources n'exposent qu'**un seul**
niveau de titre qualifiant (le cas de la plupart des projets — roman B, roman E,
Demo LN) produit des chapitres strictement **plats** (`parts == []`), exactement
comme avant l'ajout de ce mécanisme. Un 3ᵉ niveau de titre éventuel (`###`+) n'est
jamais interprété comme un découpage — il reste du texte littéral à l'intérieur de
sa Partie.

### 5.3 PDF : nettoyage du filigrane/bandeau répété

En analysant la police par bloc PyMuPDF, la même passe repère aussi les bandeaux qui
se répètent sur une grande fraction des pages (filigrane de scan, pied de page —
ex. « Page N » + une mention de site en bas de 91 % des pages de roman C) et les
**retire entièrement** du texte extrait, pas seulement de la détection de titre.
Réglages : `decoupage.mise_en_forme.footer_frac_pages` (fraction de pages minimale
pour qu'un bandeau soit considéré comme répété) et `footer_bande_page` (bande
haut/bas de la page où chercher). Deux filtres anti-faux-positifs supplémentaires :
une **liste d'exclusion** de titres à ignorer même gras/grands (`titres_exclus` :
Table of Contents, Copyright…) et l'exclusion des **doublons exacts** au même
palier (un sous-titre décoratif répété mot pour mot n'est jamais un vrai titre).

### 5.4 DOCX : styles nommés + repli mise en forme

Pandoc reste l'unique moteur de conversion docx → markdown (aucune réécriture de la
conversion elle-même). Une passe `python-docx` supplémentaire repère les paragraphes
déjà stylés « Heading/Titre 1-2 » **et** les paragraphes non stylés mais tapés à la
main en gras, dans un des 2 paliers de taille détectés — puis « promeut » la ligne
correspondante dans le markdown produit par Pandoc (préfixe `#`/`##`), en cherchant
séquentiellement le texte normalisé (accents/guillemets/emphase Markdown neutralisés).
Un candidat non retrouvé est ignoré silencieusement : l'extraction ne plante jamais
sur ce mécanisme.

### 5.4bis EPUB : le spine, la table des matières, les furigana

Un EPUB est **déjà structuré**, à l'inverse d'un PDF : le `spine` du fichier OPF donne l'ordre
de lecture, chaque document est une unité, et la table des matières nomme les sections. Il y a
donc très peu à deviner — `pipeline/epub.py` lit l'archive avec `zipfile` + `html.parser`,
**sans dépendance ajoutée**.

**Pourquoi pas Pandoc**, qui lit pourtant les EPUB et qui est déjà requis pour les `.docx` ?
Mesuré sur un light novel japonais réel de 33 documents, il produit **2,58 Mo** pour 176 ko de
texte, et il perd le contenu :

| | Pandoc | `pipeline/epub.py` |
|---|---|---|
| texte extrait | 2 578 904 car. | **176 208 car.** |
| images utilisables | 7 sur 23 | **23** |
| durée | 9,1 s | **0,4 s** |

Trois causes : les **illustrations pleine page** d'un EPUB à mise en page fixe sont des
`<svg><image xlink:href>` que Pandoc recopie en HTML brut sans émettre de lien d'image (16 des
23 images perdues) ; la chaîne Kobo enveloppe **chaque phrase** dans un `<span class="koboSpan">`
que Pandoc rend en attributs Markdown (~24 000 spans) ; et les **furigana** ressortent collés au
texte (`<ruby>七堕<rt>ナナエ</rt></ruby>` → `七堕ナナエ`, sur 8 140 ruby).

Ce que le module fait à la place :

- **ordre de lecture** = celui du `spine`, jamais celui du zip ni l'ordre alphabétique ;
- **furigana** retirés par défaut, ou conservés en `七堕(ナナエ)` avec
  `decoupage.epub.ruby: "parentheses"` — utile pour faire *relever les lectures* des noms
  propres par le terminologue, exactement l'information qui manquait côté manga (cf. §12) ;
- **titres** : une vraie balise `<h1>`…`<h6>`, sinon l'intitulé de la table des matières
  (`nav` EPUB 3 ou `toc.ncx` EPUB 2) qui pointe sur le document, sinon sa **première ligne
  courte** si elle est suivie de texte — ce dernier cas est celui du livre de référence, dont
  les chapitres s'ouvrent sur un `一` ou un `序` posé dans un paragraphe *stylé* dont la feuille
  de style de l'EPUB ne définit même pas la classe. Un document sans titre retenu ne crée pas de
  chapitre : son texte prolonge le précédent, sinon chaque page d'illustration en deviendrait un.

⚠ **Le piège du japonais.** `<span>`, `<ruby>`, `<a>` sont des éléments *inline* : joindre leur
contenu par une espace donne `千 万 丈 塔` au lieu de `千万丈塔`. Le japonais ne sépare pas ses
mots — une espace insérée à tort n'est pas une coquille de mise en forme, c'est une **erreur de
segmentation** qui se propage jusqu'au glossaire. Symétriquement, le saut de ligne du fichier
source vaut **une espace** entre deux lettres latines (sinon un EPUB anglais replié donnerait
`theenemy`) et **rien** entre deux caractères CJK. C'est la règle des navigateurs, et les deux
moitiés sont verrouillées par des tests.

### 5.5 Mise en page identique dans les 3 rendus

Chaque Partie démarre une **nouvelle page**, de façon cohérente entre les trois
formats : `epub.css` force déjà `page-break-before: always` sur `h1`/`h2` (EPUB et
PDF, qui réutilise le même CSS) ; le style `Titre2` de `templates/reference.docx`
porte désormais le même réglage (`w:pageBreakBefore`), pour un rendu Word identique.

### 5.6 Granularité de traitement : une Partie n'ajoute AUCUN passage d'agent

Question légitime : les Parties déclenchent-elles un passage complet des 5 agents
**par Partie** plutôt que par Chapitre, empêchant toute réutilisation du cache de
prompt ? **Non.** `Chapter.parts` est une métadonnée auxiliaire (affichage `--plan`,
RAPPORT.md, réinjection d'image) — elle ne crée **aucune** boucle d'orchestration
supplémentaire. Comme indiqué en section 4, le Chapitre entier reste traité en un
bloc de travail par étape, exactement comme avant.

Ce qui change réellement, c'est le **découpage en blocs** à l'intérieur d'un
chapitre : `split_blocks` regroupe les paragraphes par Partie et tolère un
dépassement de `max_block_chars` jusqu'à `decoupage.marge_partie_bloc` (20 % par
défaut) pour garder une petite Partie **entière** dans un seul bloc plutôt que de la
couper juste parce qu'elle chevauche la limite :

```
Sans tolérance (max_block_chars = 6000)        Avec marge_partie_bloc = 0.20
┌─ Bloc 1 : …fin Partie 3.4 (5800 car.) ──┐    ┌─ Bloc 1 : …Partie 3.4 (5800) +  ─┐
├─ Partie 3.5 (900 car.) COUPÉE ici ──────┤    │   Partie 3.5 ENTIÈRE (900) ───── │
│ Bloc 2 : reste de 3.5 + Partie 3.6…     │    │   = 6700 car. (≤ 6000 × 1.20)    │
└──────────────────────────────────────────┘    └────────────────────────────────────┘
```

Une Partie encore trop grosse même avec la marge retombe sur le découpage
paragraphe par paragraphe habituel (elle peut alors être scindée), sans perturber le
regroupement du contenu autour. Un chapitre sans Partie détectée (`parts == []`,
l'immense majorité des projets) n'est **jamais** affecté — le paramètre qui active
ce comportement (`has_parts`) est dérivé explicitement de `chapter.parts`, jamais
deviné en re-scannant le texte.

### 5.7 Configuration

```yaml
decoupage:
  marge_partie_bloc: 0.20   # tolérance de dépassement pour garder une Partie entière
                             # dans un bloc (0 = désactivé)
  mise_en_forme:
    ratio_taille_titre: 1.10    # taille (gras) / corps de texte, minimum pour être candidat
    footer_frac_pages: 0.30     # fraction de pages où un bandeau répété est retiré
    footer_bande_page: 0.10     # bande haut/bas de page où chercher ces bandeaux
    titres_exclus: [Table of Contents, Contents, Copyright, ...]
```

Diagnostic : `python run.py "<Projet>" <Tome> --plan`. Si le pivot ressort avec trop
peu de chapitres, ou des Parties non détectées : vérifie que les titres utilisent un
vrai style Word, ou ajuste `ratio_taille_titre` (un corps de texte inhabituellement
grand/petit décale le seuil), ajoute un motif dans `chapter_patterns`, ou force
`decoupage.detection: llm`.

---

## 6. Images

Extraction automatique dans les deux modes (docx via Pandoc, pdf via PyMuPDF, epub par
`pipeline/epub.py`), export en vraies images dans `media/`. Ensuite, deux comportements selon le mode :

- **Amélioration** (le brouillon FR porte déjà ses images) : les marqueurs `<!-- IMG: ... -->`
  restent **ancrés inline** à travers tout le pipeline — chaque agent les préserve. Les
  illustrations et séparateurs gardent donc leur place exacte, même répétés plusieurs fois
  dans le chapitre.
- **Traduction** (pas de brouillon FR) : les images sont prises depuis la langue prioritaire
  (`langues.priorite_images`, défaut `FR > EN=JP > ES=ZH`) puis réinjectées à leur **position
  proportionnelle** dans le chapitre traduit.

### Séparateurs de scène et images répétées

Une même image peut légitimement revenir des dizaines de fois : c'est le cas du **séparateur
de scène** (petite illustration marquant une rupture temporelle ou spatiale). Deux garde-fous
confondaient « répété » et « en trop », et l'effaçaient :

- le garde-fou par bloc ne gardait qu'**une** occurrence par image distincte. Il raisonne
  désormais par **quota** : la sortie d'un agent porte exactement autant d'occurrences que
  son entrée — ni plus (surplus retiré), ni moins (déficit ré-ajouté).
- le filtre anti-boucle du rendu (`_collapse_repetitions`, qui rattrape un modèle qui répète
  un passage en boucle) prenait un séparateur répété pour une telle boucle : le marqueur
  porte ses dimensions Pandoc, ce qui lui faisait franchir le seuil de « paragraphe
  substantiel » par la seule précision des flottants. Les paragraphes qui ne sont **qu'un
  marqueur d'image** en sont maintenant exemptés.

Mesuré sur un tome réel : 31 séparateurs dans la source, **5** dans le rendu avant correctif.

### Planches couleur de tête de volume

Les illustrations placées **avant le premier titre de chapitre** (planches couleur, page de
titre) étaient perdues : la détection de chapitres ne conserve que ce qui suit la première
frontière. Elles sont désormais récupérées et rendues **en préambule**, avant le chapitre 1,
dans l'ordre de la source — et écrites dans `chapters/front-matter.md` pour rester
inspectables. Elles ne passent par aucun agent (ce sont des images). Si du **texte**
substantiel se trouve aussi hors chapitres (sommaire, crédits), il n'est pas traduit et un
avertissement le signale plutôt que de le laisser disparaître en silence.

### Contrôle de comptage

`RAPPORT.md` porte une ligne `- Images : N dans la source · M dans le Markdown assemblé ·
K dans le rendu`, marquée `⚠` dès qu'un des trois nombres diffère, et `perf.log` reçoit un
avertissement si un filtre de rendu supprime un marqueur. Sans ce contrôle, les pertes
ci-dessus sont restées invisibles pendant plusieurs tomes.

**Une seule langue fournit les images, jamais plusieurs.** Le pipeline sonde les langues dans l'ordre de priorité et s'arrête à la première qui en produit réellement — toutes les autres sont extraites en texte seul (aucun fichier image écrit pour elles). Ça élimine les collisions de noms entre langues (chaque .docx/.pdf renumérote ses médias depuis 1 : les mélanger dans le même dossier `media/` écrasait/confondait les fichiers, d'où parfois « la mauvaise image »). **La taille d'affichage d'origine est préservée** (capturée à l'extraction, reportée sur le marqueur, réappliquée au rendu) : une image sortira à sa taille voulue dans le document source, pas à sa résolution native. Tu peux déplacer un marqueur à la main dans le `.md` si une illustration doit être ailleurs.

---

## 7. Prérequis

```bash
pip install -r requirements.txt          # openai, pyyaml, pymupdf, python-docx, rich
# + Pandoc (https://pandoc.org/installing.html)
# + pip install weasyprint                # moteur PDF recommandé
# + Ollama (https://ollama.com) — `ollama serve`, avec le modèle disponible (`ollama ls`)
```

### Vérifier que tout fonctionne (tests automatisés)

Une suite de tests (`tests/`, pytest) couvre les points qui ont déjà causé de vraies
régressions : schéma du glossaire (sauvegarde sans ancre YAML, squelette complet),
parseur défensif (formats mal formés du terminologue/glossariste), fusion/dédoublonnage,
remplacement `force`/accord pluriel **et ses garde-fous d'élision/de genre** (avec un test
de non-régression de perf : le remplacement doit rester linéaire, pas quadratique),
garde-fous (emballement, perte de mots, titre de Partie perdu, retry à température
réduite), fences Pandoc, tirets de dialogue, ancrage des images, détection de
chapitres/Parties (mots-clés ancrés, styles, mise en forme police+gras sur PDF et DOCX
synthétiques), tolérance de découpage par Partie, mesure de valeur ajoutée par agent
(`--diff-stages`), et `--chapitre N`. Aucun appel LLM réel n'est nécessaire (agents simulés).

```bash
pip install -r requirements-dev.txt   # pytest + psd-tools (dépendances de TEST uniquement)
pytest tests/ -v
```

`psd-tools` sert à **relire** les PSD que `manga/psd.py` écrit, avec un lecteur indépendant
(`tests/test_manga_psd_relecture.py`). Sans lui, ces tests-là sont sautés proprement et le
reste de la suite tourne — mais c'est la seule façon de valider un écrivain de format
binaire : l'analyseur maison partage les hypothèses de l'écrivain et a déjà laissé passer un
descripteur mal formé que Photoshop, lui, refusait.

À lancer après toute modification d'un prompt ou du code du pipeline, **avant** de
lancer un vrai run — ça ne remplace pas un test sur un extrait réel, mais ça détecte
en quelques secondes une régression qu'un run de plusieurs heures révélerait sinon
beaucoup plus tard (et à quel prix).

---

## 8. Utilisation — toutes les commandes

> Mémo des commandes de cette brique : **[COMMANDES.md](COMMANDES.fr.md)**.

### Interface console (recommandée)
Menu d'actions avec barres de progression — traiter un tome (avec les mêmes options
que la CLI : `--force`/`--from`/`--chapitre`/`--verbose`/`--keep-awake`/`--shutdown`),
tester le LLM, diagnostic complet, import/optimisation de glossaire, arrêt propre
d'un run en cours :
```bash
python app.py
```

### Traduire un tome
```bash
python run.py "Mon LN" Vol.1                # traite le Tome de bout en bout
python run.py "Mon LN" Vol.1 --dry-run       # exécute TOUTE la tuyauterie SANS appeler le LLM
python run.py "Mon LN" Vol.1 --force         # refait les chapitres déjà générés
python run.py "Mon LN" Vol.1 --render-only   # régénère docx/epub/pdf depuis le .md complet
```

### Traiter toute une série en une seule commande
```bash
python run.py "Mon LN" --all                          # enchaîne TOUS les tomes du projet
python run.py "Mon LN" --all --keep-awake --shutdown  # + anti-veille/extinction pour TOUTE la série
```
Un tome déjà entièrement généré est simplement **sauté rapidement**, chapitre par
chapitre — comme le fait déjà un run normal — donc relancer `--all` après coup ne
refait pas ce qui est fini. `--keep-awake`/`--shutdown` (cf. plus bas) s'appliquent
alors une seule fois pour toute la série, pas tome par tome ; un `--stop` ou un
Ctrl+C interrompt la série entière (pas seulement le tome en cours). `--force`,
`--from`, `--chapitre` et `--verbose` s'appliquent à **chaque** tome de la série.

### Relancer une seule étape, ou un seul chapitre
Après avoir modifié un prompt d'agent ou édité le glossaire, pas besoin de tout refaire : le
cache des étapes précédentes est réutilisé.
```bash
python run.py "Mon LN" Vol.1 --from correction   # refait correction → mise en page → rendu
python run.py "Mon LN" Vol.1 --from mise_en_page # ne refait que mise en page → rendu
```
Étapes valides, dans l'ordre : `terminologie`, `traduction`, `correction`, `mise_en_page`, `rendu`.

Pour itérer vite sur un prompt sans repasser tout le Tome, restreins à UN chapitre — les
autres sont réutilisés depuis leur cache tel quel :
```bash
python run.py "Mon LN" Vol.1 --chapitre 3                  # refait le chapitre 3 en entier
python run.py "Mon LN" Vol.1 --chapitre 3 --from correction # ne refait que correction→… du chapitre 3
```
`--chapitre N` suppose que le Tome a déjà été traité au moins une fois en entier (il sert à
**retester**, pas à produire d'autres chapitres au passage) ; un chapitre jamais généré et
hors cible est simplement exclu de l'assemblage, avec un avertissement.

### Glossaire (import / réintégration / optimisation / reconstruction)
```bash
python run.py "Mon LN" --import-glossary glossaire_survival.docx   # importe un glossaire existant
python run.py "Mon LN" --optimize-glossary                          # dédoublonne/fusionne/reclasse à la demande
python run.py "Mon LN" Vol.1 --extract-glossary                     # reconstruit depuis un tome DÉJÀ TRADUIT
python run.py "Mon LN" --migrate-glossary ancien.bak.yaml           # réintègre un glossaire ANTÉRIEUR
```
`--migrate-glossary` récupère un glossaire YAML qui n'est pas le fichier canonique du projet — un
`glossaire.bak.yaml`, un export, une copie d'une installation précédente, le glossaire d'une œuvre
sœur — et le convertit au format multi-cibles au passage. C'est nécessaire parce que la migration
automatique de la 2.0.0 ne se déclenche QUE sur `sources/<Projet>/glossaire.yaml` : un ancien
glossaire rangé ailleurs n'est lu par personne. Les fichiers donnés font autorité (le premier sert de
base) ; le glossaire actuel est fusionné en dernier, ou ignoré avec `--remplacer` — il part alors en
`glossaire.yaml.avant-reintegration.bak`. **Les fichiers réintégrés ne sont jamais modifiés.**
`--extract-glossary` relit le texte FR déjà fini d'un tome comme pivot et ne lance QUE la
terminologie (+ optimisation) — aucune retraduction, aucune réécriture, aucun rendu. Pratique pour
repartir d'un tome fini et propre plutôt que d'un historique de brouillons. **Reprise par bloc** :
tu peux l'arrêter (Ctrl+C ou `python run.py "Mon LN" Vol.1 --stop` depuis un autre terminal) et
relancer la MÊME commande — il repart du dernier bloc non traité au lieu de tout refaire (utile
avec le thinking, plus lent). Les checkpoints sont purgés automatiquement quand le tome est
entièrement traité.

Le glossaire étant **partagé** avec la brique manga, ces deux commandes y ont leur pendant
exact depuis la 1.8.0 — `run_manga.py "Mon Manga" --all --extract-glossary` et
`run_manga.py "Mon Manga" --optimize-glossary` (cf. §12, « Cohérence des noms propres »).

### Version
```bash
python run.py --version                  # ex. Angelith 0.9.0
python run_manga.py --version            # ex. Angelith 1.0.0 (brique manga : stable)
```
La version est déclarée **une seule fois**, dans `core/version.py` ; le
[CHANGELOG](../CHANGELOG.md) et le tag git en découlent, et `tests/test_version.py` vérifie
qu'ils ne dérivent pas. Elle est **inscrite dans ce que tu livres**, pas seulement
affichée : en-tête de run, ligne d'en-tête de `perf.log` (avec la date et la commande —
plusieurs runs s'y empilent), `- Version :` dans `RAPPORT.md`, commentaire HTML en tête du
`.md` complet, et métadonnées du fichier livré (propriété « Mots-clés » d'un `.docx`,
`dc:subject` d'un `.epub`) — de quoi identifier la version d'un fichier qui circule seul.

La règle de numérotation est **propre au projet** et documentée dans le CHANGELOG : ce
qui fait un MAJEUR ici, c'est ce qui **invalide un cache** ou t'oblige à supprimer
`build/` — une relance de tome coûte des heures de GPU. Une réécriture de prompt qui
change le caractère de la traduction est un MINEUR, et l'entrée de changelog nomme le
fichier : `git checkout v0.9.0 -- prompts/` doit permettre de reproduire la voix d'un tome.

### Diagnostic
```bash
python run.py --list                     # liste les projets disponibles, sans rien traiter
python run.py "Mon LN" --list            # liste les tomes de CE projet (marque ceux déjà générés)
python run.py --check                    # diagnostic complet : config.yaml, chemins, Pandoc,
                                          # moteur PDF, connexion Ollama (plus large que --test-llm)
python run.py --test-llm                 # teste seulement la connexion au serveur Ollama
python run.py "Mon LN" Vol.1 --plan      # chapitres + Parties détectés par langue, ordre des fichiers
python run.py "Mon LN" Vol.1 --verbose   # perf par bloc : temps, tokens, tok/s
python run.py "Mon LN" Vol.1 --diff-stages  # ce que CHAQUE agent apporte vraiment (sans LLM)
```

`--diff-stages` répond à « cet agent sert-il à quelque chose ? » en relisant les
checkpoints d'un tome **déjà traité** (aucun appel LLM). Il donne, par étape, le nombre
de blocs **réellement modifiés**, le volume de retouches, la similarité entrée/sortie —
plus une mesure ciblée :
- **les temps du récit** (narration au passé simple/imparfait) : combien de temps
  composés restaient après la traduction, et combien le correcteur en a convertis,
  **dialogues exclus** (ils gardent légitimement le passé composé, les compter rendrait
  la mesure trompeuse).

Exemple de lecture — le traducteur (agent central) produit déjà le passé simple ; la
colonne « correction » montre alors surtout les fautes résiduelles que le correcteur rattrape.
`--check` vérifie en une seule commande ce qui, sinon, ne se découvre qu'à l'échec en
plein run : sections manquantes dans `config.yaml`, chemins (`sources`/`prompts`/
`style_guide`) introuvables, Pandoc absent, moteur PDF (weasyprint ou autre)
disponible, `reference_docx`/`epub_css` présents si `docx`/`epub`/`pdf` sont dans
`rendu.formats`, puis la connexion Ollama et les modèles déclarés (comme `--test-llm`).

`--plan` affiche la hiérarchie complète Chapitre → Partie détectée pour chaque langue
(voir section 5) ainsi que l'ordre de concaténation des fichiers sources.

`--verbose` affiche après chaque bloc son temps, ses tokens générés et sa vitesse
(tok/s) — pratique pour comparer la perf à ce que tu voyais sur LM Studio, ou vérifier
que le modèle tourne bien sur GPU. Les mêmes lignes sont dupliquées dans
`build/<projet>/<tome>/perf.log`, que tu peux suivre dans un 2e terminal sans polluer
le flux principal :
```powershell
Get-Content -Wait "build\Mon LN\Vol.1\perf.log"
```
⚠ Depuis la 1.7.0, **le fichier est écrit même sans `--verbose`** (hors dry-run) : le
drapeau ne décide plus que de ce qui s'AFFICHE. Un run de nuit lancé sans lui ne laissait
jusque-là aucune trace, alors que c'est précisément la nuit qu'on en a besoin.

`perf.log` reçoit **aussi les incidents** (`⚠`) : budget « thinking » dépassé, bloc
redécoupé et relancé, repli sur le texte précédent, nouvelle tentative réseau. Chaque
ligne est préfixée du **numéro de chapitre** (`ch15 …`), pour ne plus avoir à croiser
`.checkpoints/` et `RAPPORT.md` pour savoir de quel chapitre elle parle :
```
ch15 [traduction] bloc 1/2 : 512.4s · ~12874 tok générés · ~25.1 tok/s
ch15 ⚠ [traduction] bloc 2/2 : emballement (thinking_overflow) → redécoupage en 2 et relance · 7412 c. → 3690+3720 c.
```

### Arrêter proprement / reprendre (Tomes longs)
```bash
# dans un AUTRE terminal, pendant un run :
python run.py "Mon LN" Vol.1 --stop    # les IA finissent le bloc en cours, sauvegardent, puis s'arrêtent
python run.py "Mon LN" Vol.1           # relancer reprend automatiquement au bloc suivant
```
Le travail est sauvegardé **bloc par bloc** dans `build/<projet>/<tome>/.checkpoints/`, donc la
reprise marche **même après un redémarrage du PC**. Ctrl+C dans le terminal du run fait pareil
(arrêt après le bloc en cours ; un 2ᵉ Ctrl+C force l'arrêt). Dans tous les cas — arrêt propre,
2ᵉ Ctrl+C forcé, ou erreur — le modèle est **déchargé de la VRAM avant de rendre la main**, et ce
déchargement est **blindé contre un Ctrl+C tardif** (voir « Débit GPU… » ci-dessous : privilégie
malgré tout un seul Ctrl+C, il évite d'abandonner une requête en pleine génération).

> ⚠ Si tu mets à jour `marge_partie_bloc` ou `max_block_chars` **entre deux runs**, les
> frontières de blocs d'un chapitre déjà partiellement traité (interrompu avant la mise
> à jour) peuvent se décaler par rapport à ses checkpoints existants. Utilise
> `--force --chapitre N` sur ce chapitre précis plutôt qu'une reprise simple.

> ⚠ Même logique pour le glossaire : comme `force: true` s'applique **à la sortie du
> traducteur** (et plus en fin de tome), une entrée forcée ajoutée **après** qu'un
> chapitre a été traduit ne sera pas appliquée rétroactivement par une simple reprise —
> les blocs de traduction viennent alors du cache. Relance ce chapitre avec
> `--from traduction` (ou `--force --chapitre N`) pour que la nouvelle entrée prenne effet.

### Runs de nuit / longue durée
```bash
python run.py "Mon LN" Vol.1 --keep-awake --shutdown
python run.py "Mon LN" Vol.1 --keep-awake --shutdown --shutdown-delay 300
```
`--keep-awake` empêche la mise en veille du PC **et de l'écran/GPU** pendant le run (levé
automatiquement à la fin — pas besoin de désactiver la veille globalement dans Windows). Le flag
écran est important : quand l'écran s'endort, le GPU réduit sa fréquence et l'inférence s'effondre
(un bloc peut passer de ~50 tok/s à moins de 1 tok/s). Un thread de fond ré-arme l'inhibition
toutes les 30 s pour tenir sur un run de plusieurs heures. `--shutdown` éteint le PC à la fin,
**que le run réussisse OU plante** (fini les nuits pour rien après un crash), après un délai
**annulable** (`--shutdown-delay`, défaut 120 s). Pendant le compte à rebours le terminal est
bloqué (il maintient l'anti-veille) : pour annuler, **un seul Ctrl+C dans ce terminal** suffit,
ou tape `shutdown /a` (Windows) depuis un **autre** terminal. Un
Ctrl+C manuel n'éteint jamais (tu es présent).

**Cycle de vie du modèle Ollama, automatique** : chaque run **précharge** en mémoire le(s)
modèle(s) déclaré(s) dans `config.yaml > modeles` avant de commencer (le premier bloc ne paie
pas la latence de chargement, et un modèle absent échoue tôt et clairement), puis les
**décharge** de la VRAM à la fin — **avant** toute extinction. Combiné à `--shutdown`, la
VRAM est donc libérée proprement juste avant que le PC s'éteigne. Rien à faire : c'est géré
tout seul (et sauté en `--dry-run`). Ce déchargement s'exécute via un `finally` unique **quelle
que soit la sortie** (fin, Ctrl+C, erreur) et **en ignorant SIGINT le temps de l'opération**,
pour qu'un Ctrl+C insistant ne puisse pas laisser le modèle résident en VRAM.

### Débit GPU qui chute après un Ctrl+C brutal (25 → 18 tok/s)
Symptôme : après un `Ctrl+C` en pleine génération puis une relance, le débit chute d'~25 à
~18-20 tok/s **et n'y revient qu'au reboot** ; `ollama stop` n'y change rien. Cause : un arrêt
sale abandonne la requête en cours et peut laisser le GPU (pilote AMD ROCm sous Windows) dans un
état dégradé que seul un **reset du pilote** nettoie — décharger le modèle ne suffit pas. Le
pipeline limite désormais le déclencheur (déchargement blindé, ci-dessus). Deux réglages/gestes :

- **Réglage Ollama recommandé : `OLLAMA_MAX_LOADED_MODELS=1`** (variable d'environnement système,
  puis redémarrer le serveur Ollama). Un seul modèle est utilisé par run ; deux instances de
  ~17 Go ne tiennent de toute façon pas dans 20 Go de VRAM. Ça supprime tout scénario de seconde
  instance / partage de VRAM.
- **Récupérer SANS reboot**, dans l'ordre (du plus rapide au plus lourd) :
  1. **Redémarrer complètement le serveur Ollama** (≠ `ollama stop`) : quitter « Ollama » dans la
     barre des tâches **+** `Get-Process ollama* | Stop-Process -Force`, puis relancer Ollama.
  2. Si toujours lent → **reset du pilote GPU** : `Win+Ctrl+Maj+B`, ou Gestionnaire de
     périphériques → désactiver/réactiver la carte AMD.
  3. **Reboot** en dernier recours. Le premier geste qui restaure les ~25 tok/s localise la cause.

> **Teste d'abord en dry-run** : un projet de démo est fourni
> (`sources/Demo LN/Vol.1/`, ENG en .docx + image, ESP en .pdf).
> `python run.py "Demo LN" Vol.1 --dry-run` valide extraction, découpage, images et rendu
> sans modèle chargé.
>
> ⚠ **Un dry-run ÉCRIT dans les checkpoints**, et ce qu'il y écrit est le texte **source**
> (c'est la définition du dry-run : chaque agent renvoie son `dry_payload`). Un run réel lancé
> ensuite sur le même Tome **réutilise ce cache** et produit donc un tome non traduit, sans
> rien signaler. Après un dry-run sur un Tome que tu veux vraiment traduire, lance le run réel
> avec `--force`, ou supprime `build/<Projet>/<Tome>/.checkpoints/`. Sur le projet de démo la
> question ne se pose pas.

---

## 9. Personnalisation

- **`config.yaml`** — endpoint Ollama, modèles par agent, `max_block_chars`/`max_input_tokens`,
  `marge_partie_bloc` et `mise_en_forme` (détection de chapitres/Parties, cf. section 5),
  priorités de langues/images, `sources_utilisees` (limite à 1 ou plusieurs langues, traduction
  comme amélioration), styles, formats, options du glossariste (`optimiser_apres_terminologie`,
  `optimiser_glossaire_fin_volume`), `appliquer_traductions_forcees`, `dry_run`, motifs de chapitres.
- **Glossaire par œuvre** — chaque projet a le sien : `sources/<Projet>/glossaire.yaml` (aucun
  mélange de termes entre œuvres), **catégorisé** (`personnages` avec genre/variantes/rôle, `lieux`,
  `organisations`, `créatures`, `objets` et `termes` avec `traduire`/`interdits`, `événements`,
  `groupes`, `anglicismes`). Chaque entrée expose systématiquement **tous ses champs**, même vides,
  pour être facilement complétée à la main. Copie `templates/glossaire_modele.yaml` pour démarrer,
  ou **importe un glossaire existant** : `python run.py "<Projet>" --import-glossary fichier.docx`
  (.docx/.txt/.md ; reconnaît tableaux Word, séparateurs `=`/`:`/`→`/tabulation, et sections
  Personnages / Anglicismes / Termes).

  **Génération et nettoyage automatiques.** La terminologie tourne bloc par bloc en voyant le
  glossaire **déjà construit** et le complète/corrige aussitôt (`glossaire.yaml` créé s'il n'existe
  pas, sinon **fusionné** sans écraser tes entrées). Juste après, l'agent **glossariste** dédoublonne
  et fusionne les variantes détectées (ex. Feodor/Féodor/Fwedo) avant que les autres agents ne
  s'en servent. Conséquence : les genres et orthographes restent cohérents, un genre « ? » est fixé
  dès qu'un bloc le révèle. Ce qui reste contradictoire est **signalé « ⚠ à vérifier »** dans le
  fichier et listé dans le rapport. Le glossaire d'une œuvre **plafonne naturellement** avec le temps
  (les noms propres sont en nombre fini) : c'est un bon signe, pas un problème.

  **Traduction imposée.** Ajoute `force: true` sur une entrée pour que toute forme listée en
  `variantes:`/`interdits:`/`termes_source:` soit remplacée par `nom`, **garanti**, quoi que
  produise le modèle :
  ```yaml
  creatures:
  - nom: Leprechaun          # ce sera TOUJOURS le mot utilisé au singulier
    genre: masculin           # important dès que le remplacement change de genre (cf. garde-fous)
    pluriel: Leprechauns      # optionnel : forme utilisée si un déterminant pluriel précède
    interdits: [lutin, lutins, farfadet, farfadets]
    force: true               # active le remplacement déterministe
  ```
  Le remplacement (regex, insensible à la casse, mots entiers) s'applique **dès la sortie du
  traducteur**, bloc par bloc — et non plus seulement sur le texte assemblé final. Deux
  bénéfices : le correcteur voit déjà la terminologie canonique (il ne dépense
  plus d'appels LLM à corriger ce que le déterministe corrige), et comme il tourne
  **après**, il rattrape les accords voisins qu'un regex ne sait pas réécrire.
  Désactivable via `appliquer_traductions_forcees: false`. Si `pluriel:` est fourni, un
  déterminant pluriel juste avant le mot trouvé (« les », « des », « ces », « plusieurs »…)
  déclenche cette forme plutôt que `nom` ; sans `pluriel:`, ou sans déterminant visible juste
  avant, le remplacement retombe sur `nom` au singulier (pas d'accord inventé).

  **⚠ Garde-fous : le déterministe n'introduit jamais une faute que le modèle n'aurait pas
  faite.** Un remplacement brut produisait des fautes dures, démontrées sur un vrai tome
  (`L'infirmière` → `L'médecin de combat`, `Une infirmière expérimentée` → `Une médecin de
  combat expérimentée`). Désormais :
  - **l'élision est réparée** : `l'` + cible à initiale consonne → `le`/`la` selon le `genre`
    de l'entrée (et l'inverse : `le`/`la`/`de` + cible à initiale voyelle → `l'`/`d'`) ;
  - **un remplacement dont le `genre` est inconnu, ou qui contredit le déterminant qui le
    précède** (« une » alors que l'entrée est masculine) est **refusé** et listé dans
    `RAPPORT.md` — c'est le travail du correcteur, qui peut réécrire les mots autour.
  Conséquence pratique : renseigne `genre:` sur les entrées forcées qui sont des noms
  communs. Les cas **les plus sûrs** à forcer sont ceux qui ne changent que la **casse**
  (`forces de défense` → `Forces de défense`) : aucun risque d'accord.

  **Garde-fous déterministes (`config.yaml > garde_fous`).** Indépendants de la qualité du
  modèle : si un bloc « préservation » (correcteur/mise en page) perd trop de mots par
  rapport à son entrée (`perte_mots_ratio`, ex. `correcteur: 0.75` = alerte sous 75 % du nombre de
  mots d'origine), s'il perd un titre de Partie (`##`) présent en entrée, ou si un bloc s'emballe
  (sort largement plus que sa taille attendue), le pipeline **retente une fois à température
  réduite** (`retry_temperature_facteur`, défaut ×0.4) avant de renoncer et de retomber sur la
  version précédente. Garde-fou de longueur volontairement grossier : il détecte une chute globale,
  pas un mot isolé disparu dans un bloc par ailleurs normal — ça reste principalement le rôle des
  consignes des prompts (voir `correcteur.md`).

  **Redécoupage-relance sur échec de taille (`garde_fous.redecoupage_*`).** Le retry à
  température réduite ne change rien quand le problème est que le bloc est **trop gros** :
  le modèle consomme tout son budget de raisonnement avant d'écrire sa réponse, ou dépasse
  le plafond de sortie et se met à dériver sur les sources de référence (des passages
  entiers ressortent alors **en double**). Dans ce cas — motifs `vide`, `emballement`,
  `troncature_image`, `perte_mots` — le bloc est **coupé en deux** et chaque moitié est
  relancée : plafond de sortie recalculé sur la moitié, sources de référence réalignées.
  Le résultat est la concaténation des moitiés, écrite dans le checkpoint du bloc d'origine
  (numérotation et `--from` inchangés).
  ```yaml
  garde_fous:
    redecoupage_sur_echec: true       # false = comportement historique (abandon + AMBIGU)
    redecoupage_profondeur_max: 2     # 1 → 2 sous-blocs, 2 → jusqu'à 4
    redecoupage_taille_min: 800       # en dessous, un échec n'est pas un problème de taille
  ```
  Les échecs de **consigne** (glossaire ou guide de style recopié, boucle dégénérée, titre
  perdu) ne déclenchent **pas** de redécoupage : couper n'y changerait rien et doublerait le
  coût en tokens. `RAPPORT.md` compte les redécoupages et les sous-blocs récupérés, et
  `perf.log` (avec `--verbose`) porte une ligne `⚠ … → redécoupage en 2 et relance` par
  occurrence, préfixée du numéro de chapitre.

  **Le glossaire comme dictionnaire bilingue (`termes_source`).** Une entrée peut aussi
  enregistrer le(s) mot(s) de la **langue source** (anglais, japonais…) qui lui correspondent,
  distinctement des variantes/fautes en français :
  ```yaml
  creatures:
  - nom: Homme Bête
    termes_source: [Semifer]   # le mot VU DANS LE TEXTE SOURCE, pas une variante FR
    force: true
  ```
  Deux mécanismes s'en servent : (1) le **traducteur** reçoit systématiquement les sources
  étrangères alignées au bloc en cours et utilise directement `nom` s'il reconnaît un mot de
  `termes_source` dans le texte qu'il traduit — plus besoin de le retraduire à chaque fois ;
  (2) le **terminologue**, voyant les mêmes sources, peut **compléter** une entrée existante
  avec le mot repéré (jamais en créer une nouvelle juste pour ça). Et comme `termes_source`
  est aussi inclus dans le remplacement déterministe `force: true`, un mot source oublié/laissé
  non traduit dans le texte final est quand même rattrapé.
- **Activer le raisonnement pour certains agents seulement (un seul modèle chargé).**
  Avec Ollama, le mode « thinking » se règle **par requête** (`think`), donc pas besoin
  de charger le modèle en double : on peut le laisser désactivé globalement et l'activer
  uniquement là où le raisonnement aide vraiment (terminologie, glossariste). On déclare
  un endpoint « reflexion » avec `think: true` et on y route les agents voulus :
  ```yaml
  llm:
    think: false          # défaut global : pas de raisonnement (rapide)
    endpoints:
      reflexion: {think: true}   # même modèle, même serveur, raisonnement activé
  modeles:
    terminologue: {model: "qwen3.5-9b-yumetrad", endpoint: "reflexion"}
    glossariste:  {model: "qwen3.5-9b-yumetrad", endpoint: "reflexion"}
    traducteur: "qwen3.5-9b-yumetrad"   # inchangé : think:false par défaut
  ```
  L'endpoint peut aussi pointer un autre serveur avec `base_url: "http://…:11434/v1"`.

  > **Détail technique (Ollama)** : sur l'endpoint OpenAI-compatible (`/v1/chat/completions`),
  > le paramètre natif `think` d'Ollama est ignoré ; le code traduit donc automatiquement
  > `think: true/false` en `reasoning_effort: "medium"/"none"` (le mécanisme réellement
  > pris en compte). Nécessite une version récente d'Ollama. Si un modèle continue de
  > renvoyer du vide (tout dans le champ `reasoning`), mets Ollama à jour ou ajoute
  > `PARAMETER think false` dans ton Modelfile.

  **Budget de tokens en mode thinking** : un agent qui raisonne produit un bloc
  `<think>…</think>` AVANT sa réponse. `llm.thinking_budget` (défaut 2048) est ajouté
  automatiquement à son `max_tokens` pour lui laisser la place de raisonner en plus de
  répondre — sans ça, tout le budget part dans le raisonnement, la balise fermante n'est
  jamais atteinte et la réponse ressort **vide** (symptôme : `[LLM] réponse vide…` en
  boucle sur les seuls agents « reflexion »). Augmente-le si tes blocs sont gros ou si le
  modèle raisonne longuement.

  **Pourquoi terminologue/glossariste et pas traducteur/correcteur** : comparer plusieurs sources,
  dédoublonner, trancher une ambiguïté de genre ou de classification, c'est du raisonnement —
  exactement ce que le mode réflexion est censé aider. La traduction/rédaction elle-même n'en a
  pas structurellement besoin (on l'a déjà établi : le désactiver n'a pas nui à la qualité de
  traduction), et comme ces agents tournent bloc par bloc (bien plus souvent que le glossariste,
  qui ne tourne qu'une fois par chapitre), un ralentissement s'y répercuterait beaucoup plus.
  **Conseil pour une cohérence maximale** : pré-remplis le glossaire avec les personnages
  principaux (nom canonique + genre, ex. choisir « Apple » *ou* « Pomme ») **avant** de lancer —
  la terminologie s'alignera dessus dès le premier bloc. Sinon, lance une fois, relis le
  `glossaire.yaml` généré (corrige les « ⚠ » et les doublons éventuels), puis relance avec
  `--force` — ou juste `--from traduction` si tu ne veux pas refaire la terminologie.
- **Tester le LLM** — `python run.py --test-llm` vérifie qu'Ollama répond, liste les
  modèles chargés, signale ceux manquants de `config.yaml`, et fait une mini-génération.
- **`style_guide.md`** + **`prompts/*.md`** (5 agents) — conventions et comportement de chaque agent.
  ⚠ Ces deux fichiers sont **partagés par tous les projets** : n'y mets jamais de nom de
  personnage, de lieu ou de réplique tirée d'une œuvre précise (un exemple concret dans une
  instruction peut se retrouver recopié littéralement dans une traduction sans rapport). Décris
  les règles de forme abstraitement, ou avec un espace réservé générique. Les 4 prompts d'agents
  d'écriture distinguent explicitement une ligne `##` (titre de Partie — à **traduire** mais à
  garder seule sur sa ligne, jamais fondue dans la prose) d'un marqueur `<!-- IMG: -->`/
  `<!-- AMBIGU: -->` (jamais traduit, verbatim).
- **`templates/reference.docx`** — **ton** fichier de styles (déjà en place), y compris le
  saut de page avant chaque Partie (style `Titre2`, cf. section 5.5). **`templates/epub.css`** —
  style EPUB/PDF.

---

## 10. Limites (honnêtes)

- **Alignement ANCRÉ sur le pivot** : le pivot (FR en mode amélioration) fixe le nombre de
  chapitres. Une source au **même nombre** s'aligne chapitre par chapitre ; une source au nombre
  **différent** (sur- ou sous-détectée) a son texte complet **découpé proportionnellement** sur les
  chapitres du pivot. Conséquence : une mauvaise détection sur une *référence* (ex. EN qui détecte
  ses sous-sections, ZH non découpé) ne casse plus l'alignement — seule la détection du **pivot**
  doit être fiable. Les écarts sont signalés dans le rapport et par `--plan`.
- **Tirets de dialogue** : avec `dialogue_dash_in_text: false`, le tiret `—` est retiré du texte
  au rendu (le style Word « Paragraphe de liste » et le CSS EPUB l'ajoutent), pour éviter le
  double tiret « — — ».
- **Contexte par bloc** : règle `max_block_chars` selon ton modèle. Très long chapitre → plus de
  blocs (plus lent).
- **Fenêtre de contexte & glossaire volumineux** : le prompt d'un bloc est borné par
  `decoupage.max_input_tokens` (24000 par défaut). Règle : `num_ctx` (Modelfile Ollama) ≈ `max_input_tokens`
  + 6000 de marge — monte les deux si tu as la VRAM (jusqu'à la limite de ton modèle). Le
  **glossaire injecté** dans les prompts est lui-même plafonné (~la moitié de ce budget) : au-delà,
  il bascule automatiquement en version **compacte** (sans les descriptions), puis tronque en
  dernier recours. Le prompt ne peut donc **jamais déborder** la fenêtre de contexte, même sur un
  glossaire très volumineux accumulé au fil des tomes.
- **Contamination par du contenu instructif** : les fichiers partagés entre projets (`style_guide.md`, `prompts/*.md`) ne doivent JAMAIS contenir de nom de personnage, de lieu ou de réplique d'une œuvre précise — un exemple concret dans une instruction peut se retrouver recopié littéralement dans une traduction, même sans rapport. Les marqueurs `<!-- IMG: ... -->` / `<!-- AMBIGU: ... -->` sont décrits par préfixe (`commence par <!-- IMG:`) plutôt que par un exemple complet, pour la même raison.
- **Fences Pandoc mal formées** : le garde-fou déterministe au rendu reconstruit en bonne et due forme (3 lignes : ouverture, texte, fermeture) toute fence que le modèle aurait écrite en ligne (motif régulier : `::: {.dialogue ...} texte :::` tout sur une seule ligne, invisible pour Pandoc — d'où un `{.dialogue custom-style="..."}` littéral dans le document final sinon), et nettoie aussi les `:::`/`::` hallucinées en pleine phrase. Un `custom-style` qui ne correspond à aucun style réel de `reference.docx` (nom hallucine ou mal orthographié) est neutralisé de la même façon (cf. section 2) — jamais transmis tel quel à Pandoc.
- **Annotations de correction glissées dans le texte** : un garde-fou déterministe retire toute parenthèse du type `(Correction : "X" au lieu de "Y")` qu'un agent aurait narrée en plein texte au lieu de la garder pour lui.
- **Emballement du modèle (boucles)** : un petit modèle peut parfois partir en boucle et générer
  des milliers de tokens pour un seul bloc (très lent). La génération est donc **plafonnée**
  automatiquement, proportionnellement à la taille du bloc ; si un bloc sature ce plafond (ou —
  pour correcteur/mise en page — perd trop de mots ou un titre de Partie par rapport à son
  entrée), un **retry à température réduite** est tenté avant de renoncer ; en cas d'échec
  persistant, le texte précédent est conservé (marqué `AMBIGU` dans le rapport pour l'emballement/
  le vide ; silencieux pour la perte de mots/titre, comptabilisée dans le résumé de `RAPPORT.md`).
  Pour réduire les boucles à la source, règle un **Repeat Penalty** ~1,05-1,1 dans les paramètres
  du modèle Ollama (et Top K ~20).
- **Garde-fou anti-perte-de-mots** : volontairement grossier (ratio de mots global par bloc) —
  il rattrape une chute massive (phrase/paragraphe perdu), pas un mot de liaison isolé disparu
  dans un bloc par ailleurs de longueur normale (ex. un « l' » manquant sur 200 mots ne fait pas
  bouger le ratio de façon détectable). Le principal rempart contre ce cas précis reste les
  consignes des prompts (traducteur/correcteur), pas ce filet de sécurité. Le titre de Partie perdu
  (`##`) a en revanche son propre garde-fou dédié (section 4), car il ne fait pas bouger ce ratio.
- **Traductions forcées (`force: true`)** : la détection du pluriel repose sur un déterminant
  visible juste avant le mot trouvé (« les », « des », « ces », « plusieurs »…) ET sur la présence
  du champ `pluriel:` dans l'entrée. Sans l'un ou l'autre, le remplacement retombe sur `nom` au
  singulier — pas d'accord inventé au hasard. Les formes plurielles doivent être listées
  **explicitement** dans `interdits:` (`infirmière` ne fait pas correspondre `infirmières`).
  Seul le **déterminant** est réaccordé, pas les adjectifs/participes autour : « L'infirmière
  était épuisée » → « Le médecin de combat était épuisée » (« épuisée » reste au féminin). C'est
  assumé, précisément parce que le forçage a lieu **avant** la correction, qui rattrape
  ces accords. Un remplacement dont le genre est incertain est **refusé** plutôt que fautif, et
  listé dans `RAPPORT.md` (voir section 9).
- **`--extract-glossary`** : reprend par bloc ET par chapitre en cas d'arrêt (Ctrl+C ou
  `--stop`) — relance la même commande pour continuer. Un chapitre entièrement traité
  (blocs + optimisation du glossaire) est marqué terminé et intégralement sauté à la
  reprise : ni les blocs, ni l'optimisation (appel LLM coûteux) ne sont refaits. Les
  checkpoints (dans `build/<projet>/<tome>/.checkpoints_glossaire/`) sont purgés quand le
  tome est fini.
- **`--chapitre N`** : suppose qu'un run complet a déjà eu lieu au moins une fois (il sert à
  retester un chapitre déjà généré, pas à en produire d'autres au passage) ; un chapitre hors
  cible jamais généré est exclu de l'assemblage plutôt que produit à la volée.
- **Détection des chapitres/Parties** : voir section 5 pour le détail complet (cascade de
  signaux, hiérarchie à 2 niveaux, config `decoupage.mise_en_forme`). Limite à garder en tête :
  la détection par mise en forme dépend de seuils configurés (`ratio_taille_titre` notamment) —
  un livre avec un corps de texte inhabituellement grand ou petit, ou une mise en forme très
  irrégulière, peut nécessiter d'ajuster ces seuils plutôt que de fonctionner « à l'aveugle ».
- **PDF scanné** (image sans texte sélectionnable) → aucun titre détectable, traité comme un seul
  chapitre (le découpage en blocs prend le relais).

---

## 11. Arborescence

Trois couches, dans ce sens de dépendance et jamais l'inverse : **`core/`** (socle partagé)
← **`pipeline/`** / **`manga/`** / **`scan/`** (les trois briques) ← **`run.py`** /
**`run_manga.py`** / **`run_ocr.py`** / **`app.py`** / **`gui.py`** (les interfaces).

**`scan/`** (§13) est la seule brique qui en importe une autre : elle prend son OCR japonais
à `manga/`. La dépendance est à sens unique et assumée — réécrire la résolution du cache
hors ligne et le figeage de révision de `manga/ocr.py` n'aurait produit qu'un second endroit
où les corriger. Avec le reste du dépôt, son couplage n'est pas du code mais un **fichier** :
elle écrit un `.md` que `pipeline/sources.py` sait déjà lire.

La couche des interfaces s'est élargie sans se déformer : **`gui/` ne contient que du Qt**.
Écrire une région, relire une bulle, retraduire une réplique, tenir un document avec son
historique, lettrer une planche — tout cela vit dans `manga/` (`edition.py`,
`traduction_unitaire.py`, `document.py`, `rendu.py`, `services.py`), en Python nu, et se
teste avec `pytest` sans que PySide6 soit installé. C'est la même règle que celle qui
interdit à `app.py` de dépendre d'une CLI, poussée d'un cran.

La frontière du socle n'est pas « ce qui est dupliqué » mais **« ce qui prend l'unité de
travail en paramètre »** : les deux orchestrateurs ne diffèrent que par leur unité (un bloc de
texte dans un chapitre / une planche de bulles). Appeler un modèle, diagnostiquer une mauvaise
réponse, retenter à température corrigée, compter des tokens, rapporter — tout cela est
*paramétré par* l'unité, pas *défini par* elle, et vit dans `core/`. Ce qui **construit**
l'unité (découpage en chapitres, détection de bulles) reste dans sa brique. Deux tests
verrouillent le sens des dépendances : `tests/test_core_alias.py` et
`tests/test_core_cli.py`.

Neuf modules de `pipeline/` ont été déplacés dans `core/` au lot 2.1 ; ils laissent derrière
eux un **alias** de trois lignes (`sys.modules[__name__] = _impl`, jamais
`from core.x import *`) pour que les imports historiques continuent de marcher, avec
`pipeline.agents is core.agents`.

```
angelith/
├── run.py                    # CLI light novel (projet + tome, commandes de la section 8)
├── run_manga.py              # CLI manga (section 12)
├── run_ocr.py                # CLI OCR de scans (section 13)
├── run_illustration.py       # CLI atelier d'illustration — UNE commande, EXPÉRIMENTAL, désarmé
├── app.py                    # interface console (TUI) — ne dépend d'aucune CLI
├── gui.py                    # interface graphique (§12) — runs + édition des planches
├── illustration/             # 4e brique : images NEUVES. N'IMPORTE QUE core/ (testé)
│   ├── frontiere.py          # le périmètre d'écriture, armé PENDANT le run
│   ├── moteur.py             # l'interface, les cinq canaux, la requête gelée, le factice
│   ├── requete.py            # requete.yaml — le format relu par l'humain, et sa porte
│   ├── marquage.py           # LE seul chemin qui écrit un PNG : tEXt + sidecar (AI Act)
│   ├── poids.py              # téléchargement de plusieurs Go, repris sur coupure
│   ├── comfyui.py            # un client HTTP, pas un framework
│   ├── juge.py               # lot 25 : l'encodeur ONNX et les TROIS grandeurs, en numpy
│   ├── identite.py           # lot 25 : la voie A — références de la bible → canal du moteur
│   ├── prompt.py             # lot 26 : la charpente DÉTERMINISTE — rien n'entre hors bible
│   ├── selection.py          # lot 26 : quelles images montrer, et POURQUOI (retenues + écartées)
│   ├── scene.py              # lot 26 : la POSE, tirée du texte — jamais un attribut
│   ├── gabarits/             # lot 26 : la SYNTAXE d'un modèle d'image, pas la voix d'un tome
│   ├── atelier.py            # qui est illustrable, avec quelles images — Python nu, testable
│   ├── relecture.py          # lot 27 : L'ÉCRAN de relecture, et la PORTE vers la phase 2
│   ├── galerie.py            # lot 27 : garder / jeter / purger, l'inventaire, le poids disque
│   ├── progression.py        # lot 27 : préparation (LLM) · bascule · génération (image)
│   ├── attente.py            # lot 27 : le chiffre qui décide de la FORME de l'atelier
│   ├── vram.py               # lot 27 : la bascule — s'ouvre une fois, se ferme TOUJOURS
│   ├── sonde.py              # lot 28 : ce que le serveur expose RÉELLEMENT — en lecture seule
│   ├── validation.py         # lot 28 : les 5 vérifications d'un graphe, AVANT le GPU
│   ├── console.py            # les QUESTIONS, et rien d'autre (rich). La façade console
│   ├── orchestrateur.py      # les deux phases, la bascule VRAM
│   └── rapport.py            # RAPPORT.md et perf.log — DANS le dossier de la brique
├── gui/                      # QT SEULEMENT : aucune logique métier ici
│   ├── fenetre.py            # fenêtre, destinations, journal, un seul run à la fois
│   ├── bandeau.py            # lot 32 : le bandeau de run, visible depuis TOUTES les destinations
│   ├── avancement.py         # temps restant OBSERVÉ + ce que le bandeau écrit — sans Qt
│   ├── atelier.py            # lot 27 : l'onglet « Atelier » — catalogue, puis RELECTURE
│   ├── editeur.py            # éditeur de planche (zones, répliques, « Appliquer »)
│   ├── scene_planche.py      # canevas : image, zones, outils de tracé
│   ├── lanceur.py            # lancement des runs (manga ET light novel)
│   ├── modele_tome.py        # lecture SEULE du cache (projet.json d'abord)
│   └── travailleur.py        # QThread + ReporterQt (le Reporter du socle, en signaux)
├── scan/                      # BRIQUE 3 : lire un LN japonais livré en images (§13)
│   ├── grille.py             # analyse de mise en page — colonnes, ruby, coupes, SANS modèle
│   ├── lecture.py            # OCR des tranches (le seul modèle chargé de la brique)
│   ├── assemblage.py         # colonnes → paragraphes → markdown (pur, sans E/S)
│   ├── checkpoints.py        # cache par PAGE (un tome coûte ~2 h)
│   ├── orchestrator_scan.py  # balayage en deux passes, arrêt propre
│   ├── report_scan.py        # RAPPORT.md — les pages à vérifier avant de traduire
│   ├── pages.py              # inventaire du dossier de langue
│   └── apercu.py             # image de contrôle de l'analyse (--apercu)
├── config.yaml
├── COMMANDES.md               # mémo : toutes les commandes des trois briques
├── style_guide.md
├── requirements.txt
├── tests/                     # suite pytest (voir section 7)
│   ├── conftest.py
│   ├── test_agents.py
│   ├── test_glossary.py
│   ├── test_glossary_build.py
│   ├── test_images.py
│   ├── test_render.py
│   ├── test_orchestrator.py
│   ├── test_split.py             # détection de chapitres/Parties + tolérance de découpage
│   ├── test_formatting.py        # clustering police+gras (module partagé PDF/DOCX)
│   ├── test_extract_formatting.py # extraction PDF/DOCX pilotée par la mise en forme
│   ├── test_stagediff.py         # mesure de valeur ajoutée par agent (--diff-stages)
│   └── test_llm.py
├── prompts/                  # 6 prompts d'agents (éditables)
│   ├── terminologue.md
│   ├── traducteur.md
│   ├── correcteur.md
│   ├── mise_en_page.md
│   └── glossariste.md        # optimisation/dédoublonnage du glossaire
├── core/                      # SOCLE partagé par les deux briques (ne dépend d'aucune)
│   ├── version.py             # source unique de vérité de la version (§8 « Version »)
│   ├── config.py              # héritage racine → brique par FUSION PROFONDE (llm, chemins)
│   ├── agents.py              # Agent + build_agents UNIQUE (section=/names=/agent_cls=)
│   ├── llm.py                 # client Ollama (API compatible OpenAI)
│   ├── quality.py             # plafond de sortie, retry à température corrigée, registre de motifs
│   ├── runtime.py             # inventaire/branchement/agrégation/fermeture des clients LLM
│   ├── report.py              # squelette commun des RAPPORT.md (en-tête, stats LLM, troncature)
│   ├── cli.py                 # fragments de CLI, anti-veille/extinction, sections de doctor
│   ├── glossary.py            # schéma catégorisé, sauvegarde lisible, rendu pour les prompts
│   ├── glossary_build.py      # fusion incrémentale + parsing défensif des relevés du terminologue
│   ├── glossary_import.py     # import .docx/.txt/.md
│   ├── glossary_force.py      # forçage `force: true` (élision + accord français)
│   ├── control.py             # --stop / reprise propre par unité de travail
│   ├── power.py               # --keep-awake / --shutdown (anti-veille, extinction programmée)
│   ├── reporter.py            # avancement (texte + rich) + perf.log
│   ├── progression.py         # lot 32 : phases, objet en cours, fraction MONOTONE — sans Qt
│   └── tokens.py              # estimation de tokens (CJK ~1/caractère, latin ~4 caractères/token)
├── pipeline/                  # brique LIGHT NOVEL
│   ├── extract.py            # docx (Pandoc) + pdf (PyMuPDF) → texte + images ; détection de
│   │                          # titres par style ET par mise en forme (police+gras)
│   ├── epub.py                # epub (zipfile + html.parser) : ordre du spine, furigana,
│   │                          # illustrations en SVG, titres par table des matières
│   ├── formatting.py          # clustering police+gras partagé (corps de texte, paliers de titre)
│   ├── stagediff.py            # valeur ajoutée par agent depuis les checkpoints (--diff-stages)
│   ├── split.py                # hiérarchie Chapitre → Partie + découpage en blocs (avec tolérance)
│   ├── sources.py              # scan d'un Tome (langues, pivot, images, mode)
│   ├── images.py               # ancrage inline / réinjection proportionnelle des illustrations
│   ├── doctor.py               # diagnostic de l'environnement LN (--check) — utilisé aussi par app.py
│   ├── orchestrator.py         # enchaînement chapitre/blocs, glossariste, traductions forcées, rapport
│   ├── render.py               # Markdown → docx/epub/pdf ; neutralise les custom-style inconnus
│   └── agents.py, llm.py, control.py, power.py, reporter.py, tokens.py,
│                               # glossary*.py — ALIAS de trois lignes vers core/ (lot 2.1)
├── templates/
│   ├── reference.docx          # TON fichier de styles (Titre2 : saut de page avant chaque Partie)
│   ├── epub.css                 # style EPUB/PDF
│   └── glossaire_modele.yaml    # modèle catégorisé à copier dans chaque nouveau projet
├── tools/
│   ├── make_template.js         # (re)génère un reference.docx si tu n'as pas le tien
│   ├── banc.py                  # LE banc : tous les volumes de build/ en un tableau daté
│   ├── _banc_commun.py          # lecture de cache PARTAGÉE par les cinq outils ci-dessous
│   ├── _banc_detection.py       # rappel / précision / F1 contre une vérité terrain (COCO)
│   ├── corpus_synthetique.py    # génère le corpus annoté, redistribuable sans réserve
│   ├── compter_variantes.py     # orthographes bannies subsistantes + dérives pas encore bannies
│   ├── mesurer_bulles.py        # distribution géométrique des bulles (lit le cache, n'écrit rien)
│   ├── apercu_detection.py      # ce que donnerait une relance de détection — une seule inférence
│   ├── verifier_ordre.py        # l'ordre de lecture persisté contre le sens déclaré
│   ├── valider_psd_photoshop.ps1 # ouvre un PSD dans Photoshop (COM) et vérifie que le texte se réécrit
│   └── installer_polices.ps1    # installe les polices de lettrage (par utilisateur, réversible)
├── sources/
│   ├── <Projet>/glossaire.yaml  # glossaire catégorisé, propre à l'œuvre (tous ses tomes)
│   └── Demo LN/Vol.1/           # projet de démonstration (dry-run)
└── build/<Projet>/<Tome>/
    ├── <Projet>_<Tome>.md       # Markdown complet
    ├── chapters/chNN.md
    ├── media/
    ├── .checkpoints/             # cache par bloc — conservé après le rendu, permet --from
    ├── RAPPORT.md
    ├── <Projet>_<Tome>.docx
    ├── <Projet>_<Tome>.epub
    └── <Projet>_<Tome>.pdf
```

## 12. Manga (brique indépendante)

> Mémo des commandes de cette brique : **[COMMANDES.md](COMMANDES.fr.md)**.

Traduction de **bande dessinée** (planches/images — manga, webtoon) : détection des bulles →
OCR de la langue source → traduction → nettoyage déterministe → réinjection du texte français. **Totalement
indépendante** du pipeline LN ci-dessus : package séparé (`manga/`), CLI séparée
(`run_manga.py`), section de config séparée (`config.yaml > manga:`), sortie séparée
(`build/<Projet>/<Tome>/manga/`).

**Indépendante, mais plus isolée** : depuis le lot 2, les deux briques partagent le socle
`core/` (§11) — client LLM, construction des agents, héritage de config, moteur de garde-fous,
cycle de vie des clients, squelette de rapport, fragments de CLI. L'isolement précédent avait
un coût mesuré : la brique manga ignorait silencieusement `endpoint:`, perdait
`llm.endpoints` dès qu'on définissait un bloc `manga.llm`, dupliquait `sources`/`build` dans
`manga.chemins`, envoyait ses incidents LLM sur stdout au lieu de `perf.log`, laissait une
socket pendante à chaque run et n'avait ni `--keep-awake` ni `--shutdown`. Ce qui reste propre
au manga l'est vraiment : détection, nettoyage, lettrage, ordre de lecture, motifs d'échec.

### Principe : l'IA ne dessine jamais
Détection et OCR ne font que **lire** l'image. Les seules écritures de pixels sont
déterministes : `manga/clean.py` remplit le masque de bulle détecté avec sa couleur
de fond mesurée, `manga/typeset.py` y dessine le texte traduit (Pillow), et
`manga/effacement.py` — ajouté au lot 22, **désarmé par défaut** — reconstruit le fond d'une
zone hors bulle par remplissage de couleur ou par diffusion en numpy. Aucun modèle
génératif ne touche au dessin. Vérifié par `tests/test_manga_clean.py` (tout pixel
hors du masque ressort bit-à-bit identique à l'original).

#### La portée du principe, écrite le 2026-08-29 — décision d'Alexandre

Le principe porte sur les **pixels de l'œuvre** : aucune écriture non déterministe dans une
planche, une page ou un fichier source. Une brique qui ne modifie **aucun** fichier existant
n'entre pas dans son périmètre : elle produit des fichiers neufs, dans un dossier qui lui est
propre, marqués comme générés, et supprimables sans rien casser. L'effacement de pixels
existants, lui, reste interdit hors du cadre que le lot 22 a défini.

C'est ce qui rend la quatrième brique — `run_illustration.py`, ajoutée au lot 24 — compatible
avec le principe **sans le renégocier** : elle lit `media/`, elle écrit sous
`build/<Projet>/illustrations/` et — pour ce qu'un humain décide de garder, depuis le lot 27 —
sous `sources/<Projet>/illustrations/`, un sous-dossier NEUF ; elle ne composite rien dans une
planche ni dans une page. Les quatre occurrences du principe dans le code restent vraies mot
pour mot.

⚠ **Et l'insertion du lot 27 ne les contredit pas non plus.** Armée, elle ajoute des
*paragraphes* au Markdown assemblé du light novel — un marqueur d'image et sa légende — sans
réécrire un seul caractère du récit ni toucher un pixel. Elle est désarmée par défaut
(`illustration.inserer_dans_sorties: false`), et la légende « Illustration générée par IA — ne
fait pas partie de l'œuvre originale » n'a **aucun interrupteur** : `core/insertion.py` lève
sur une légende vide.

⚠ **Cette portée n'est pas un précédent pour l'effacement.** Le lot 22, lui, portait bien sur
des pixels de l'œuvre ; il a tranché **contre** le modèle génératif, et sa décision est
ci-dessous, inchangée. Les deux sujets ne se mélangent pas.

⚠ **Et elle n'est pas seulement affirmée.** Le dépôt ne se contente jamais d'un raisonnement
là où un test existe — `clean.py` garde son `paint &= region.mask` « parce que l'invariant ne
doit pas dépendre d'un raisonnement ». Même exigence ici, à deux niveaux :
`illustration/frontiere.py` refuse **à l'exécution** toute écriture hors du dossier de la
brique, et `tests/test_illustration_frontiere.py` vérifie qu'un run complet laisse **toutes**
les empreintes SHA-256 préexistantes de l'arbre inchangées.

#### La décision du lot 22, tranchée par écrit avant d'écrire le code

Le `PLAN-22` demandait d'arbitrer explicitement une question que ce principe tranchait par
effet de bord : il interdit **à la fois** qu'un modèle génératif réécrive des pixels de dessin
dans le chemin par défaut, **et** qu'un utilisateur qui le demande obtienne un calque
d'effacement séparé et réversible. Ce sont deux choses très différentes sous le même mot.

**La décision retenue est le refus du modèle génératif, et le principe reste écrit en cinq
mots.** Trois raisons, dans l'ordre où elles pèsent :

1. **Le garde-fou du lot 21 rend le modèle inutile aujourd'hui.** Un effacement n'est autorisé
   que sur une zone `lecture_sure` — deux voies de lecture indépendantes qui s'accordent. Le
   taux de `lecture_sure` mesuré sur les six tomes du corpus est de **0 %**
   (`docs/mesures/sfx-2026-08-28.md`). Payer plusieurs gigaoctets de poids pour reconstruire le fond de
   zones qu'on s'interdit d'effacer serait acheter la seconde moitié d'un pont.
2. **Le matériel ne le porte pas.** `Qwen-Image-Edit` fait 20 milliards de paramètres
   (Apache-2.0, vérifié) ; la contrainte réaliste écrite au dossier du projet est déjà « un
   modèle de 27 milliards de paramètres sur un GPU grand public », occupé par la traduction.
3. **La licence des poids `big-lama` n'a pas pu être établie sur une source primaire.** Le
   *code* de LaMa est Apache-2.0 ; ses poids circulent sous des conditions divergentes. Le
   dépôt porte déjà deux poids sous contrainte (GPL-3.0 amont, Manga109-s académique) ; un
   troisième rendrait la redistribution indéfendable.

**Ce qui est ajouté, en revanche, est un effacement DÉTERMINISTE**, et il ne renégocie rien :
remplir un masque d'encre dilaté avec la couleur de fond mesurée, c'est exactement le mode
`"texte"` de `clean.py`, transposé hors de la bulle. Il obéit à quatre règles :

- **désarmé par défaut** (`manga.onomatopees.effacement.mode: "aucun"`) — un utilisateur qui ne
  touche à rien obtient le rendu bit à bit identique ;
- **jamais sur une zone dont la lecture n'est pas concordante** — la règle est dans le code,
  aucune clé de configuration ne la désarme ;
- **rien n'est peint** sous le seuil d'uniformité du fond local (0,35, le palier du gratte-ciel
  de la page 44) : la zone garde son texte source, visible donc corrigible ;
- **calque séparé**, jamais aplati sans qu'on l'ait demandé, listé dans `RAPPORT.md`, et
  annulable en masquant un calque dans le PSD ou en supprimant un fichier de cache.

### Installation
```
pip install -r requirements-manga.txt
python run_manga.py --check          # récupère les modèles et vérifie l'environnement
```
**Les deux modèles se téléchargent tout seuls** au premier usage : `manga-ocr` récupère
le sien, et le détecteur de bulles (~104 Mo) est pris en charge depuis la v0.20.0 —
`--check` le fait au bon moment, quand tu prépares la machine plutôt qu'au milieu d'un
tome. Pour le figer, le remplacer ou repasser en manuel (proxy…), voir
`manga_models/README.md` et `config.yaml > manga.detection.telechargement_auto`.

Une fois en cache, l'OCR est chargé **depuis le disque et sans réseau**
(`manga.ocr.hors_ligne: "auto"`). Sans cela, chaque lancement rappelait Hugging Face pour
revalider la révision : latence, avertissement « unauthenticated requests », run impossible
hors ligne — et une nouvelle révision pouvait arriver **en plein tome** et changer l'OCR sans
prévenir. La barre `Loading weights: 264/264` qui défile au démarrage n'est pas un
téléchargement : c'est le chargement disque, en moins d'une seconde.

### Structure des sources
```
sources/<Projet>/<Tome>/<FORMAT>/<LANGUE>/*.cbz | *.cbr | *.png/*.jpg/*.webp
```
Plusieurs archives sont concaténées dans l'ordre de lecture (tri naturel).

**Les deux niveaux sont facultatifs**, avec repli en cascade — la structure historique
`<Tome>/manga/` continue de marcher à l'identique :

| Sur disque | format | langue source |
|---|---|---|
| `<Tome>/manga/*.png` | `manga` | `manga.langue_source` (défaut `jp`) |
| `<Tome>/*.png` | `manga` | `manga.langue_source` |
| `<Tome>/manga/ENG/*.png` | `manga` | anglais — lecture **droite→gauche** |
| `<Tome>/webtoon/ENG/*.png` | `webtoon` | anglais — lecture **gauche→droite** |

Les noms de dossiers de langue sont ceux du light novel (`config.yaml > langues.dossiers` :
`ENG`, `JAP`, `FR`, `ESP`, `CHINOIS`…). `--langue ENG` et `--format webtoon` forcent le choix
quand un tome porte plusieurs sources.

> ⚠ **Format et langue sont deux axes indépendants, et les confondre coûte cher.** Un scan
> **anglais** d'un manga japonais se lit toujours droite→gauche ; un webtoon **coréen** se lit
> gauche→droite. Le format fixe le sens de lecture — donc l'ordre dans lequel les bulles sont
> numérotées pour le modèle —, la langue fixe le moteur d'OCR et les consignes.

> ⚠ **Ce que vaut réellement le webtoon aujourd'hui, mesuré.** Le format tourne de bout en
> bout, mais **une détection sur six ou sept y est fausse** (15 à 17 % de bulles sans texte,
> contre **0 %** sur les neuf volumes de manga paginé), et une bande de 10 000 px rend ~6 bulles
> là où sa surface en promettrait 25 à 35. Les bulles fausses sont repeintes puis recollées
> — le dessin d'origine revient — et `RAPPORT.md` les liste sous « Zones RESTAURÉES ». C'est
> une limite connue et chiffrée, pas une panne : le détecteur livré n'a jamais été entraîné sur
> du webtoon. Le détail, avec ce qui a été essayé et écarté :
> [`webtoon-2026-08-26.md`](mesures/webtoon-2026-08-26.md).

**La langue source choisit le moteur d'OCR**, et ce n'est pas un réglage de confort :
`manga-ocr` est un modèle *japonais*, dont le décodeur n'a pas de token d'espace. Sur une
planche anglaise il ne rend pas un texte approximatif, il rend une chaîne collée parsemée de
kanji inventés (`HE'S CERTAINLY NO ORDINARY PERSON` → `ＨＥＳＣＥＲＴＡＮＡＹＮＯ…`), que le
modèle de traduction traduit ensuite sans broncher. Les sources non japonaises passent donc
par **RapidOCR** (`pip install rapidocr-onnxruntime`, cf. `requirements-manga.txt`) ; le
japonais garde `manga-ocr`, où il est imbattable.

**Un manga déjà en français** (`<Tome>/manga/FR/`) ne se traduit pas : un run complet s'arrête
avec un message renvoyant vers `--extract-glossary`, qui sait le relever sans rien traduire.

**Un chapitre est un `<Tome>`.** Une œuvre découpée en chapitres se range donc à plat, et
chacun produit son propre CBZ, son propre `RAPPORT.md` et ses propres checkpoints :

```
sources/Mon Manga/
├── glossaire.yaml          ← PARTAGÉ par tous les chapitres (et par le light novel)
├── Chap.6/manga/*.jpg          ← source japonaise supposée (structure historique)
├── Chap.7/manga/*.jpg
└── Chap.10/manga/*.jpg
```

L'ordre de traitement est l'ordre de **lecture**, pas l'ordre alphabétique (`Chap.10` vient
après `Chap.9`). Ce n'est pas cosmétique : la passe terminologique enrichit `glossaire.yaml`
au fil des chapitres, et les traiter dans le désordre donnerait au chapitre 2 un glossaire
nourri du chapitre 10.

### Utilisation
```
python run_manga.py "Mon Manga" Vol.1              # traduit le tome
python run_manga.py "Mon Webtoon" Chap.11 --format webtoon --langue ENG  # force format et langue
python run_manga.py "Mon Manga" Vol.1 --dry-run     # détection/OCR réels, SANS appel LLM
python run_manga.py "Mon Manga" Vol.1 --force       # refait TOUTES les étapes des pages déjà générées
python run_manga.py "Mon Manga" Vol.1 --stop        # arrêt propre (reprise à la relance)
python run_manga.py "Mon Manga" Vol.1 --lot 20      # 20 planches par appel LLM (cf. ci-dessous)
python run_manga.py "Mon Manga" Vol.1 --lot 20 --think   # …avec raisonnement du traducteur
python run_manga.py "Mon Manga" Vol.1 --extract-glossary  # peuple le glossaire, sans rien traduire
python run_manga.py "Mon Manga" --all --extract-glossary  # …sur toute l'œuvre (cf. §12 glossaire)
python run_manga.py "Mon Manga" --optimize-glossary       # dédoublonne le glossaire de l'œuvre
python run_manga.py --check                          # diagnostic (dépendances, modèle, Ollama)
python run_manga.py --list                            # œuvres disponibles
python run_manga.py "Mon Manga" --list                # état RÉEL de chaque chapitre
python run_manga.py "Mon Manga" Vol.1 --keep-awake --shutdown   # run de nuit (cf. §8)
```

### Traiter toute une œuvre : `--all`

```
python run_manga.py "Mon Manga" --all --keep-awake --shutdown
```

Enchaîne **tous les chapitres restants**, dans l'ordre de lecture, avec un seul
préchargement de modèle et une seule extinction pour toute la série.

**Ce qui est déjà fait n'est pas rouvert.** Un pré-vol en lecture seule (`manga/serie.py`)
compare le nombre de planches rendues au nombre de planches source, puis vérifie qu'aucune
n'est en retard sur ses données. Ouvrir un chapitre fini n'est pas gratuit : `assemble_outputs`
réécrit le CBZ inconditionnellement — 230 Mo pour *manga A* Vol.1. Mesuré sur trois
chapitres déjà traités : **629 ms** pour tout constater, contre 3 min 9 s pour les rouvrir.

`run_manga.py "Mon Manga" --list` montre exactement ce que le pré-vol voit :

| Puce | Statut | `--all` le traite ? |
|---|---|---|
| `·` | jamais traité | oui |
| `◐` | partiel — run interrompu, ou planches en échec | oui, il reprend |
| `↻` | à relettrer — le rendu est en retard sur les données | oui, **relettrage ciblé** |
| `✓` | complet et à jour | **non**, sauté sans être ouvert |
| `⚠` | aucune image ni archive (ex. un dossier de light novel) | non |

⚠ Un chapitre `↻` demande une consigne explicite, et c'est contre-intuitif : son cache est
**complet**, seul l'ordre d'écriture est en cause. `stages_to_redo` ne lit que la présence des
fichiers, jamais leurs `mtime` — il conclurait « rien à faire » et chaque planche serait sautée.
Le chapitre ressortirait donc « à relettrer » après son propre passage, et chaque nuit le
reprendrait pour rien. `--all` vise donc ses seules planches en retard (`--from rendu` +
`only_pages`), plutôt que d'en relettrer 150 pour une.

**Une nuit survit à ses accidents.** Un chapitre qui lève n'interrompt pas les suivants ; une
planche qui lève n'interrompt pas son chapitre (elle est nommée dans le `RAPPORT.md` du
chapitre, avec sa commande de reprise). Seuls `--stop` et Ctrl+C arrêtent franchement la
série — c'est une demande, pas un accident. `python run_manga.py "Mon Manga" --all --stop`
depuis un autre terminal arrête la série entière, et non le seul chapitre nommé.

Au matin, `build/<Œuvre>/RAPPORT-SERIE.md` dit l'état de chaque chapitre, ce que le run a
fait, et ce qui reste ; `build/<Œuvre>/perf.log` est le journal de la série, suivable en
direct (`Get-Content -Wait`). Le code de sortie vaut **1** si un chapitre a échoué ou si un
chapitre traité reste incomplet — mais pas après un arrêt demandé.

**Harmoniser l'œuvre après la nuit :**

```
python run_manga.py "Mon Manga" --all --from rendu
```

Le glossaire a grossi de tous les chapitres. Cette passe relettre l'œuvre entière avec sa
version finale, **sans un seul appel LLM** (forçage `force: true`). ⚠ `--from` et `--force`
annulent le saut du pré-vol : sans quoi cette commande ne toucherait aucun chapitre fini,
c'est-à-dire exactement ceux qu'elle vise.

`--keep-awake`/`--shutdown`/`--shutdown-delay` se comportent exactement comme côté light
novel (section 8, « Runs de nuit / longue durée ») : mêmes flags, même code
(`core/cli.py`). Ils sont plus utiles encore ici — un tome de 150 planches avec le
raisonnement activé dépasse les deux heures. Le modèle est **préchargé** avant la première
planche et déchargé à la fin (VRAM libérée, d'autant plus utile si la détection ONNX tourne
sur le même GPU), sauf avec `--from rendu`, qui n'appelle jamais le LLM : y monter un modèle
de 27 B pour rien — et évincer à la fin celui que tu avais peut-être chargé pour autre
chose — serait un pur gaspillage.

### Traduction par lots de planches (`--lot`)

Par défaut, **une planche = un appel LLM**. `--lot N` (ou `manga.lot.planches` dans
`config.yaml`) met **N planches consécutives dans le même appel**, jusqu'à 20. Sur un tome de
131 planches, `--lot 20` fait **7 appels au lieu de 131** : le glossaire, la fiche de contexte
de l'œuvre et le prompt système ne sont plus payés en prefill qu'une fois par lot.

C'est aussi ce qui rend le **raisonnement** abordable. À une planche par appel, il faisait
passer un tome de ~24 min à 1 h 15 – 2 h 50 ; en lot, la trace est payée une fois pour 20
planches. D'où `--think`, qui n'a de sens qu'accompagné de `--lot`.

**Le lot n'est jamais retenté en entier.** Il se dégrade planche par planche vers le chemin
normal :

- si le modèle n'a numéroté **aucune** ligne, le lot est abandonné et les N planches sont
  reprises une par une (rattacher 130 répliques par leur seul ordre serait indéfendable) ;
- s'il manque une réplique à **une** planche, seule celle-là est refaite — et pas si la bulle
  manquante est vide à raison (OCR sans aucun texte, comme `（）`).

Au pire, on retombe donc exactement sur le coût et le résultat de `--lot 1`.

⚠ **Ce que le lot coûte.** L'unité d'arrêt propre **et l'unité de perte** passent de 1 à N :
un `--stop` ou une panne en milieu de lot fait reperdre le lot entier (les traductions d'un lot
ne sont écrites qu'après leur rattrapage, comme toujours). Le retour est aussi différé — rien
ne s'affiche avant la fin du lot. **Pour itérer sur un prompt, garder `--lot 1`.**

⚠ **En mode vision**, le lot est plafonné à `manga.lot.planches_vision` (4) : une image pleine
page par planche saturerait le contexte avant la première réplique.

⚠ **Le `num_ctx` doit suivre.** Renseigne la vraie valeur du Modelfile dans `llm.num_ctx`
(65 536 par défaut) : c'est elle qui permet au garde-fou d'avertir quand un lot ne tient pas,
au lieu de le découvrir à la troncature. À vérifier avec
`ollama show <modèle> --modelfile | Select-String num_ctx`.

Le champ `lot_taille` de `qa.json` dit, planche par planche, combien de planches partageaient
son appel — 1 pour une planche reprise seule. `RAPPORT.md` en donne le bilan.

### Reprise PAR ÉTAGE (checkpoints)
Chaque page passe par plusieurs étapes, **chacune mise en cache sur disque** sous
`build/<Projet>/<Tome>/manga/` : `detection` (bulles+masques) → `nettoyage` (pages
« clean ») → `ocr` (texte japonais) → `terminologie` → `traduction` (texte français) →
`sfx` (texte hors bulle) → `rendu` (page finale). Une page déjà terminée peut être
**relancée à une SEULE étape**, sans refaire les précédentes :
```
python run_manga.py "Mon Manga" Vol.1 --from traduction  # regloss./retraduit + relettre
                                                          # (garde détection/nettoyage/OCR)
python run_manga.py "Mon Manga" Vol.1 --from rendu        # relettre SEULEMENT — repart des
                                                          # pages clean + traductions déjà en
                                                          # cache (ex. après un changement de
                                                          # police ou une correction manuelle)
python run_manga.py "Mon Manga" Vol.1 --page 3             # ne (re)traite QUE la page 3
python run_manga.py "Mon Manga" Vol.1 --page 3 --from ocr  # ne refait que OCR→rendu de la page 3
python run_manga.py "Mon Manga" Vol.1 --from sfx           # relit/retraduit le texte HORS bulle
                                                           # (n'effleure ni l'OCR des bulles ni
                                                           # la traduction de planche)
```
`sfx` est un **frère** de `detection`, pas un maillon de la chaîne : il ne dépend que des
masques de bulles — pour écarter le texte déjà pris en charge par un ballon — et n'alimente
que le rendu. C'est ce qui permet d'activer la passe sur un tome déjà traduit sans dépenser
un seul appel LLM de traduction de planche.
Les pages **« clean » (bulles vidées, SANS texte)** sont dans
`build/<Projet>/<Tome>/manga/pages_clean/` — un dossier normal, directement
consultable, et le point de départ de `--from rendu`. Le reste du cache (masques,
OCR, traductions) vit sous `.checkpoints/page_XXXX/` (miroir manga du cache par bloc
du LN, cf. section 4).

### Suivi de performance (--verbose)
Comme côté LN, `--verbose` affiche après CHAQUE étape de CHAQUE page le temps
écoulé — `detection`, `nettoyage`, `ocr`, `rendu` — et, pour `traduction` (seul
appel LLM du pipeline manga), les tokens générés et la vitesse (tok/s) :
```
python run_manga.py "Mon Manga" Vol.1 --verbose
```
Les lignes sont aussi dupliquées dans `build/<Projet>/<Tome>/manga/perf.log`,
suivable dans un 2e terminal (`Get-Content -Wait …\perf.log`). En fin de tome, un
résumé (appels LLM, tokens générés, vitesse moyenne) est affiché — indépendamment
de `--verbose`.

### Modèle LLM et mode de traduction
Réutilise par défaut le **même modèle Ollama** que le LN (`qwen3.6:27b`, déjà
vision-capable — vérifiable via `ollama show qwen3.6:27b`). Trois modes
(`config.yaml > manga.mode_traduction`) :
- `"texte"` (défaut) : traduit depuis le texte OCR seul — rapide.
- `"vision"` : envoie EN PLUS la planche entière, pour **toutes** les planches du tome —
  plus lent (encodage image), et c'est le coût maximal pour les 90 % de planches qui n'en
  ont pas besoin.
- `"cible"` (2.7.0) : le premier passage est textuel, et c'est le **diagnostic** qui décide,
  planche par planche, d'une seconde tentative avec image. Une planche dont le premier essai
  déclenche un motif d'échec *est* une planche ambiguë ; ce sont alors les **crops de ses
  groupes** qui partent, pas la planche entière — cinq à dix fois plus légers, et bien plus
  lisibles parce que le sujet occupe le cadre. Une planche qui passe du premier coup ne coûte
  rien de plus.

### Ce que le traducteur sait de la planche (2.7.0)

Depuis la 2.7.0, l'énoncé porte la **structure** de la planche, calculée sans le moindre
appel LLM (`config.yaml > manga.structure`) :

- des **groupes** de bulles séparés par une rupture de mise en page — ce ne sont pas des
  cases détectées, et le prompt le dit ;
- un **type de bulle** quand la forme est nette : `(pensée)`, `(récitatif)`, `(cri)` ;
- une **étiquette de locuteur** `[A]` / `[B]`, déduite de la direction des queues de bulle,
  **locale à la planche** et annoncée comme seulement probable.

⚠ La règle qui gouverne les trois : **l'annotation absente vaut mieux que l'annotation
fausse**. Mesuré sur les 7 862 bulles des dix volumes de `build/`, **86,2 % des bulles
restent sans type**. C'est voulu, et c'est le chiffre à surveiller quand on touche aux seuils :

```
python tools/mesurer_structure.py --tous            # la distribution, sans charger un modèle
python tools/mesurer_structure.py --tous --profils  # + les centiles bruts
```

Le glossaire de l'œuvre (`sources/<Projet>/glossaire.yaml`, **partagé avec le LN**)
est automatiquement injecté en contexte du traducteur manga si présent, pour garder
les mêmes noms entre le light novel et son manga.

### Reprise, cache et coût d'une relance

Les étapes ne forment **pas une chaîne** mais un graphe : `ocr` lit l'image d'origine et les
régions, jamais la page nettoyée. `nettoyage` et `ocr` sont donc des *frères*, tous deux
issus de `detection` seule :

```
detection ──┬── nettoyage ─────────────────────────┐
            └── ocr ── terminologie ── traduction ─┴── rendu
```

`--from <étape>` ne recalcule que l'étape demandée et ce qui en **dépend réellement**.
Concrètement, sur le tome de 150 planches :

| Commande | Ce qui est refait | Coût |
|---|---|---|
| `--from rendu` | lettrage seul (+ forçage du glossaire) | ~5 min, 0 appel LLM |
| `--from nettoyage` | nettoyage + lettrage | ~3 min, 0 appel LLM |
| `--from terminologie` | relevé des noms + traduction + lettrage | ~1 h + LLM |
| `--from ocr` | OCR + traduction + lettrage | ~40 min + LLM |
| `--from detection` | tout | heures, modèle ONNX requis |

**`terminologie` est la seule étape dont un cache ABSENT ne périme rien**, et c'est
indispensable : `terminologie.txt` n'existe sur aucune planche d'un tome traduit avant le lot
3. Si son absence invalidait la traduction comme le fait celle de l'OCR, un simple
`--from nettoyage` déclencherait la retraduction des 150 planches. L'étape écrit dans le
glossaire de l'**œuvre**, pas dans le cache de la page ; son fichier ne sert qu'à ne pas
repayer l'appel LLM. Pour la (re)lancer, c'est `--from terminologie`, explicitement.

`--from nettoyage` et `--from rendu` n'ont besoin **ni du modèle ONNX ni de `manga-ocr`** :
les régions viennent de `.checkpoints/`, et les deux modèles ne sont chargés qu'à leur
premier usage réel.

`--assembler` n'exécute que l'assemblage (CBZ/PDF) depuis `pages_out/`, sans rien
retraduire — utile après un arrêt, ou pour changer de format.

### `RAPPORT.md`

Chaque page persiste son contrôle qualité dans `.checkpoints/page_XXXX/qa.json`, et le
rapport est bâti en relisant **toutes** les pages, cache compris. C'est délibéré : une page
réutilisée du cache ne produit aucune statistique fraîche, si bien qu'un rapport construit
sur le seul run en cours serait quasi vide sur une reprise — donc mensonger.

Il liste les pages sans bulle, les écarts de comptage bulles/traductions, les traductions
vides, les détections à faible confiance, les bulles non nettoyées, les glyphes substitués ou
supprimés, et les formes canoniques que le glossaire n'a pas pu forcer.

Un texte qui ne tient pas dans sa bulle a **quatre causes**, et trois d'entre elles n'ont
rien à voir avec le traducteur — le rapport les sépare, parce qu'il conseillait
« raccourcir la traduction » neuf fois sur le Vol.1 et n'avait raison qu'une seule :

| cause | ce que ça veut dire | correctif |
|---|---|---|
| **région dégénérée** | la région ne peut porter aucun mot, même au plus petit corps — elle n'est **pas lettrée** | corriger la **détection** |
| **police trop large** | la région est saine, mais le mot le plus long ne tient pas au plus petit corps **dans cette police-là** — elle est lettrée quand même | raccourcir la réplique, ou changer `manga.typeset.font_path` |
| **bulle étroite** | le mot le plus long ne tient pas en largeur | corriger la **détection**, ou scinder la région |
| **texte trop long** | la bulle pourrait accueillir du texte, il y en a trop | raccourcir la **traduction** |

⚠ La frontière entre les deux premières s'est payée cher. Le critère de largeur dépend de
la police, et une police 1,3× plus large a fait basculer deux vraies bulles du côté
« dégénéré » : le nettoyage ayant déjà effacé le japonais, elles sont sorties **blanches**,
et le message accusait une détection qui n'avait pas bougé. Désormais la géométrie seule
fait renoncer — aire utile, hauteur utile, et une largeur où pas même une lettre ne tient.
Une réplique non dessinée a sa propre section de rapport, en tête des incidents : c'est le
seul où du texte disparaît de la planche.

Plutôt que de déborder — un débordement fait *découper les lettres par le masque* — le lettrage
descend sous `taille_min`, jusqu'à `taille_min_absolue`. Ces bulles-là ont leur propre section :
elles sont lisibles, mais leur petite taille dit qu'il reste quelque chose à corriger en amont.

Il dit aussi **comment** les répliques ont été rattachées à leurs bulles. Le modèle répond
par une liste numérotée ; on honore les numéros présents et on laisse vides les bulles sans
numéro. Deux cas méritent un coup d'œil, et un seul est grave :

- **numérotation incomplète** — des bulles restent vides. Signalé, sans risque de décalage.
- **repli positionnel** — le modèle n'a numéroté *aucune* ligne, elles sont rattachées dans
  l'ordre : **l'alignement n'est pas garanti**, une réplique peut être lettrée dans la
  mauvaise bulle. Rien dans l'image ne le laisse voir, d'où la section dédiée. Une relance
  `--page N --from traduction` est la réponse.

### Rattrapage des bulles vides

Une bulle laissée vide alors que sa source porte du texte est **retraduite seule** : une bulle,
une réponse, aucun numéro à se tromper. Relancer la page entière rejouerait la numérotation,
c'est-à-dire exactement ce qui vient d'échouer — mesuré sur le Vol.1, les deux retries de page
ont échoué comme leur premier essai. Coût sur ce tome : **un appel court**.

Trois garde-fous, sous `manga.rattrapage` :

- une source qui ne porte **aucun texte** n'est pas rattrapable — l'OCR `（）` de la page 8 n'a
  rien à traduire, et l'inventer serait pire que la bulle vide ;
- au-delà de `max_par_page` (3), on ne rattrape **rien** : ce n'est plus un trou mais une
  planche ratée, à reprendre par `--page N --from traduction` ;
- une réponse **diagnostiquée est rejetée** (numérotée, japonais recopié, disproportionnée). Une
  mauvaise réplique dessinée dans une bulle est pire qu'une bulle vide, qui est au moins listée
  au rapport.

Les bulles rattrapées ont leur propre section : elles ont été traduites *hors du contexte de leur
planche*, donc sans les répliques voisines qui désambiguïsent un pronom ou un sujet implicite.

### Retoucher une planche dans Photoshop (export PSD)

Les sorties `images`, `cbz` et `pdf` sont **aplaties** : corriger une réplique imposait de
relancer le pipeline, et rien ne permettait de déplacer un bloc de texte de trois pixels.
Ajoute `"psd"` à `manga.rendu.formats` et chaque planche sort aussi en fichier Photoshop
**à calques**, dans `build/<Projet>/<Tome>/manga/pages_psd/` :

```
Texte 12 — « Une journée banale »          T   un calque par bulle, du haut vers le bas
Texte 11 — « Montre ton front ! Pourquo… » T
…
Planche nettoyée                           ▣   bulles vidées : le fond sur lequel relettrer
Planche originale                          ▣   le scan, MASQUÉ — pour comparer
```

Chaque calque de bulle est borné à sa bulle, ce qui le rend léger et déplaçable sans toucher
au reste.

Deux réglages, sous `manga.rendu` :
- `psd_texte` — `"type"` (**défaut**) écrit de vrais **calques de texte** : police, corps,
  couleur, et réécriture au clavier. `"rasterise"` n'écrit que des pixels : déplaçables,
  redimensionnables, effaçables, mais il faut retaper pour changer un mot.
- `psd_original: false` — n'inclut pas le scan d'origine, un tiers du poids du fichier.

⚠ **C'est le poste le plus lourd de la sortie, et il est actif par défaut.** Mesuré sur 469
écritures réelles : **8,5 Mo par planche**, soit **1,3 Go pour un tome de 150 planches** —
**68 %** des 1,9 Go que pèse le tome complet (contre 226 Mo pour `pages_out/` et 222 Mo pour
`pages_clean/`).

Le défaut reste `true` parce que le PSD est la seule porte de sortie vers une retouche
manuelle, et qu'on ne devine pas quelle planche en aura besoin. Mais si tu ne retouches pas
sous Photoshop, `manga.rendu.psd_original: false` allège d'un tiers, et couper la génération
ramène un tome à ~0,6 Go. Le temps d'écriture apparaît désormais dans `perf.log` sous
`[psd]`, à côté du poids — jusqu'ici la ligne annonçait la taille sans jamais dire son prix.

**Le mode `type` ne coûte rien en fidélité.** Le calque porte à la fois nos pixels *et*
l'information de texte : la planche composée par Photoshop est **identique au pixel près** à
celle que le lettrage a dessinée — mesuré, 0 pixel d'écart sur 1 800 000 — et le texte n'est
re-rendu que le jour où on le modifie. Une bulle en **débordement** reste rasterisée : sa mise
en page n'est plus celle qu'un calque de type saurait reproduire, et des pixels justes valent
mieux qu'un calque éditable faux.

> **Valider par le moteur de Photoshop, pas par un lecteur tiers.** Écrire un calque de texte
> conforme demande un bloc `TySh` et une `EngineData` corrects, et **trois tentatives ont
> échoué** faute d'une boucle de retour : alerte « Problèmes à la lecture des calques » puis
> dégradation en pixels (v0.18/0.19.0), plantage à l'ouverture sans même un message (v0.19.1),
> repli prudent sur `rasterise` (v0.21.0). `psd-tools` valide la conformité à la
> *spécification* ; Photoshop valide ce qu'Adobe *accepte* — et c'est le second qui décide.
>
> ```
> python run_manga.py --psd-test
> powershell -ExecutionPolicy Bypass -File tools/valider_psd_photoshop.ps1
> ```
> Le script ouvre le fichier via l'automation COM, affirme le type de chaque calque **selon
> Photoshop**, et tente une réécriture avant de refermer sans enregistrer. C'est la seule
> preuve qui compte : un calque peut être déclaré de type, s'afficher correctement, et refuser
> malgré tout l'outil Texte. Outil manuel (il ouvre l'application), donc jamais dans pytest ;
> à relancer après toute modification de `manga/psd.py`.

**Installe la police de lettrage, une fois.** Un calque de texte ne peut pas embarquer sa
police : il n'en déclare que le nom, et Photoshop la cherche parmi celles **installées**. Sans
elle, « Polices manquantes » à chaque ouverture — et, plus gênant, une **substitution dès la
première modification** : la bulle réécrite change de dessin et jure avec ses voisines.

```
powershell -ExecutionPolicy Bypass -File tools/installer_polices.ps1
```

Pour ton compte utilisateur, sans droits administrateur, réversible (`-Desinstaller`) et
idempotent. Redémarre Photoshop ensuite — il ne relit sa liste qu'au démarrage. Le validateur
ci-dessus interroge `Application.Fonts` et nomme les polices absentes, ce qui évite d'ouvrir
une planche pour le découvrir.
> Sinon, garde `"rasterise"` et signale-le.

**Poids et coût, mesurés** sur une planche de 1125×1600 à 12 bulles : **7,2 Mo** — 2,4 Mo pour
le scan d'origine, 2,0 Mo pour la planche nettoyée, ~2,7 Mo pour l'aperçu aplati, et **0,01 Mo
pour les douze calques de texte réunis**. Soit ~1,1 Go pour un tome de 150 planches (~700 Mo
sans le scan), et le rendu d'une planche passe de ~0,3 s à ~2,4 s. À n'activer que si tu comptes
vraiment retoucher.

⚠ **Ce qui est vérifié, et ce qui ne l'est pas.** Le fichier est écrit en Python pur (aucune
dépendance ajoutée) et sa structure est vérifiée par un analyseur PSD indépendant, dans les
tests : en-tête, nombre et noms de calques, rectangles, canaux, chaîne retrouvée dans le moteur
de texte, et **aperçu aplati identique au pixel** à `pages_out/`. En revanche **aucun Photoshop
n'a ouvert ces fichiers** — il n'y en a pas sur la machine de développement. Le risque est borné
par le format lui-même : un calque de texte porte *aussi* ses pixels, donc si Photoshop refusait
son moteur de texte, le calque se comporterait comme un calque rasterisé et on ne perdrait que
la réécriture au clavier.

Enfin, si Photoshop ne trouve pas la police du lettrage il **substitue** et le signale : le
calque reste éditable, le dessin change. Installer `templates/fonts/ComicNeue-Bold.ttf` (ou ta
police) côté système règle le cas.

### Changer la police de lettrage

`config.yaml > manga.typeset.font_path`, puis `--from rendu` — le lettrage est la seule
étape rejouée, les traductions restent en cache.

⚠ **Deux pièges, tous deux silencieux avant qu'on les mesure.**

1. **La police est choisie BULLE PAR BULLE.** S'il manque un seul caractère à la police
   demandée, toute la réplique est redessinée dans la première police de repli qui la
   couvre — et cette bascule n'était signalée nulle part. Mesuré sur un tome de 150
   planches, avec une police à qui manquaient `« » œ Ç À — ♪` : **63 bulles sur 818, sur
   45 planches**, sorties dans une autre police. Le **pré-vol** le dit désormais dans les
   premières secondes du run, et `python run_manga.py --check` sans lancer de run.
   `python tools/completer_police.py <ta_police.ttf>` complète la police à partir de ses
   propres tracés (⚠ travail dérivé : cf. `NOTICE`).
2. **Une police plus large change la mise en page.** Le pré-vol annonce le rapport à
   ComicNeue-Bold à corps égal. Au-delà de ~1,15×, attends-toi à des corps plus petits et
   à des bulles étroites en débordement (cause `police trop large` du tableau ci-dessus).

Un chemin Windows se met en guillemets **simples** dans `config.yaml` : en guillemets
doubles, YAML lit `\` comme une échappe, `\U` réclame 8 chiffres hexadécimaux et le
chargement échoue — tandis que `\t` passerait en silence en produisant une tabulation.

### Cohérence des noms propres

Le glossaire de l'œuvre est le **même fichier** que celui du light novel
(`sources/<Projet>/glossaire.yaml`) : c'est ce qui garde les noms cohérents entre un roman et
son manga. Il sert à trois choses, de la moins chère à la plus chère.

**1. Forçage (`force: true`) — déterministe, zéro appel LLM.** Toute forme listée en
`variantes`/`interdits` est remplacée par `nom` dans les bulles, avec la gestion française de
l'élision et de l'accord (mêmes garde-fous que le light novel : un remplacement qui
introduirait une faute d'accord est **refusé et signalé** plutôt que appliqué). Puis
`--from rendu` réécrit le tome.

C'est le levier qui compte, parce que le défaut est massif. Chaque planche est traduite en
isolation : le modèle ne sait pas quelle romanisation il a retenue vingt planches plus tôt.
Mesuré sur *manga A* Vol.1, avant/après un `--from rendu` :

| Source | Rendus par le modèle | Après forçage |
|---|---|---|
| `カタフラクト` | Kataphrakt · Katafrakt · Kataphrakto · Cataphracte | **Kataphrakt** |
| `リベルティナ` | Libertina (13) · Ribitina · Libidina | **Libertina** (15) |
| `クルーテオ` | Kuran (2) · Cluteo · Kruuteo | **Cruhteo** (4) |
| `アセイラム` | Aselam (4) · Asylum | **Asseylum** (5) |
| `三影` (kanji) | Mitsukage (12) · Mikage · Miyage | **Mitsukage** (13) |
| `弥月` (kanji) | Yuzuki (6) · Miyuki (4) · Yozuki | **Yuzuki** (11) |

Total : **39 orthographes bannies → 0**, en 5 minutes et sans un seul appel LLM. Les deux
dernières lignes sont les plus parlantes — ce sont des **kanji**, strictement identiques d'une
bulle à l'autre. Aucune ambiguïté de lecture OCR ne l'explique.

Pour recompter à tout moment :
```
python tools/compter_variantes.py "Mon Manga" Vol.1          # ce que le lecteur voit
python tools/compter_variantes.py "Mon Manga" Vol.1 --brut   # la sortie brute du modèle
```
Sans glossaire, l'outil bascule en mode exploratoire et propose les familles de variantes
candidates — c'est ainsi qu'on établit la première liste.

**1 bis. Détection de dérive — déterministe, zéro appel LLM.** Le forçage ne rattrape que ce
qu'on lui a listé, et les `interdits` décrivent les fautes des runs **précédents** : un run
neuf en produit de nouvelles. Sur le Vol.1, `compter_variantes.py` annonçait « 0 forme bannie »
— exact, et trompeur. La brique cherche donc elle-même les formes proches d'un nom du
glossaire, avec **trois niveaux de preuve** :

| niveau | preuve | écrit `interdits` | corrige |
|---|---|---|---|
| **T1 ancrée** | un `termes_source` japonais de l'entrée est dans l'OCR de la **même bulle** | oui | **ce run** |
| **T2 dominance** | le nom domine le tome (≥ 5 occurrences et ≥ 3 × le candidat) | oui | `--from rendu` |
| **T3 lexicale** | proximité seule | non | rapport seulement |

La comparaison se fait **toujours contre un nom du glossaire**, jamais entre mots : c'est ce
qui écarte `Désolé ~ Désolée` ou `Comte ~ Vicomte`, que la simple proximité remontait. S'y
ajoutent une longueur minimale de 5 caractères (`Vers` est à distance 1 de « Mers » : limite
assumée), un budget d'édition proportionnel, et une garde de pluriel — `Kataphrakts` n'est pas
une faute, c'est un champ `pluriel:` qui manque, et le rapport le propose comme tel.

Réglages sous `manga.terminologie` (`actif`, `min_occurrences`, `dominance`). Les dérives vont
en `interdits`, **jamais en `variantes`** : `variantes` est la clé de recherche du
dédoublonneur, y déposer une faute corromprait une future fusion.

**2. Injection en contexte — gratuite.** Le glossaire est donné au traducteur à chaque
planche : les planches suivantes convergent d'elles-mêmes, y compris sur des formes que le
forçage ne peut pas atteindre (déclinaisons, formes non listées).

**3. Relevé automatique (`terminologue`, optionnel) — un appel LLM par planche à traduire.**
Décommenté dans `config.yaml > manga.modeles`, il relève les noms propres depuis le **japonais
OCR** (et, sur un tome déjà traduit, depuis le français produit — de quoi lister les variantes
en `interdits`) et enrichit le glossaire de l'œuvre. Le `glossariste` dédoublonne ensuite.
Chaque relevé est mis en cache (`.checkpoints/page_XXXX/terminologie.txt`) : une reprise ne
repaie rien.

Le relevé passe sur **tout le volume avant la première traduction**, et le dédoublonnage juste
après : les 150 planches sont donc traduites avec le même glossaire, complet et propre. Le
traitement se fait pour cela en deux balayages du tome —

```
A. par planche : détection → nettoyage → OCR        (aucun appel LLM)
B. tout le volume : relevé terminologique → dédoublonnage du glossaire
C. par planche : traduction → forçage → lettrage → rendu
```

Jusqu'au lot 4.1 les six étapes s'enchaînaient planche par planche, et c'était la cause du
tableau ci-dessus : la planche 1 était traduite avec un glossaire **vide**, le dédoublonnage
tombait après la dernière traduction (il ne profitait donc qu'au run suivant), et le contexte
du traducteur changeait à chaque planche. Conséquence pratique du découpage : sur un tome
neuf, aucune planche traduite n'apparaît avant que les 150 ne soient détectées et OCRisées.

⚠ Dans un run de traduction, une planche n'est relevée que si elle va être **traduite** —
c'est ce qui garantit qu'une planche déjà faite ne coûte aucun appel par surprise. `--page 7`
ne coûte donc qu'un seul relevé, les notes des autres planches étant relues depuis le cache,
ce qui reconstitue le glossaire du volume gratuitement.

**3 bis. Peupler le glossaire SANS traduire — `--extract-glossary`.** La règle ci-dessus avait
une conséquence coûteuse : sur une œuvre déjà traduite, enrichir le glossaire imposait de la
**retraduire** (`--from traduction`). Des heures de GPU, les `pages_out/` réécrites et les CBZ
réencodés — 230 Mo par chapitre, sur un dossier synchronisé — pour un résultat qui tient dans
un YAML de quelques kilo-octets. C'est le pendant manga de `run.py --extract-glossary` :

```
python run_manga.py "Mon Manga" Vol.1 --extract-glossary   # un chapitre
python run_manga.py "Mon Manga" --all --extract-glossary   # toute l'œuvre (run de nuit)
python run_manga.py "Mon Manga" --optimize-glossary        # dédoublonnage (glossariste)
python run_manga.py "Mon Manga" Vol.1 --from rendu         # applique le résultat aux bulles
```

Ce qui tourne, et rien d'autre : détection et OCR des planches qui n'en ont pas encore, relevé
de **toutes** les planches, détection de dérive. Ce qui ne tourne pas : nettoyage, traduction,
lettrage, `RAPPORT.md`, archive. Rien n'est écrit hors de `.checkpoints/` et du glossaire, et
c'est vérifié par `tests/test_manga_glossaire.py` — c'est cette promesse qui rend la commande
lançable sur une œuvre finie.

Trois conséquences pratiques :

* un chapitre **vierge** marche aussi : la commande peut servir à établir le glossaire *avant*
  la première traduction, et non seulement après ;
* sur un chapitre **déjà traduit**, le relevé voit le français produit, donc liste les
  variantes en `interdits` — et les deux niveaux de dérive T1/T2 sont rejoués sur tout le
  chapitre, ce qu'un run normal ne faisait que pour les planches qu'il retraduisait ;
* le **dédoublonnage est payé une seule fois**, après le dernier chapitre, et seulement si le
  glossaire a bougé : le glossariste travaille sur le glossaire entier de l'œuvre, le rappeler
  par chapitre serait quinze appels pour un seul résultat.

`--force` refait aussi les relevés en cache (après avoir modifié `prompts/terminologue.md`) ;
`--dry-run` fait la détection et l'OCR pour de vrai mais **n'écrit pas** le glossaire, qui est
une source de l'utilisateur et non un artefact de build ; `--stop` et `Ctrl+C` s'arrêtent
proprement, l'acquis étant sauvé après chaque planche qui change quelque chose.

⚠ Le forçage s'applique à l'**usage**, pas à l'écriture du cache : `traduction.json` garde la
sortie brute du modèle. C'est délibéré et c'est ce qui rend l'itération gratuite — corrige une
orthographe dans le glossaire, relance `--from rendu`, les 150 planches sont réécrites sans
LLM. Le light novel, lui, force à la traduction, parce que son correcteur travaille ensuite
sur ce texte ; la brique manga n'a aucun agent en aval.

### État de la brique et feuille de route

Depuis la **1.0.0**, `run_manga.py --version` annonce `brique manga : stable`. Ce que cela
recouvre, mesuré sur les 258 planches à bulles des deux tomes du *manga A* :
**257 en numérotation complète**, **0 repli positionnel**, **0 kanji résiduel** sur 1 593
bulles.

⚠ Ce que cela ne recouvre PAS : la **lecture** du texte hors bulle. `manga-ocr` est un modèle
de dialogue et invente sur une onomatopée stylisée — d'où `manga.onomatopees.mode: "rapport"`
par défaut, qui détecte, lit, traduit et **rapporte** sans rien dessiner sur la planche. Les
bulles, elles, ne sont pas concernées.

**L'édition directe annoncée ici est livrée** (section « Interface graphique » ci-dessous).
Le numéro **2.0.0 reste à poser** : il le sera quand l'interface aura fait ses preuves sur de
vrais tomes. Rien de ce qu'elle écrit ne lui est spécifique — `run_manga.py` relit et réécrit
exactement les mêmes fichiers.

### Interface graphique (`python gui.py`)

```powershell
pip install -r requirements-gui.txt     # PySide6, ~120 Mo — optionnel
python gui.py
python gui.py --config autre.yaml
```

Un fichier de dépendances **séparé**, comme `requirements-manga.txt` : `run.py`, `run_manga.py`
et `app.py` fonctionnent sans qu'une seule de ces lignes soit installée.

**Onglet « Planches » — l'éditeur.** À gauche la liste des planches, au centre la page rendue
avec les zones de bulles superposées **et leur numéro d'ordre de lecture**, à droite
l'inspecteur (OCR, réplique, origine).

Le numéro est ce qu'il y a de plus utile à l'écran : c'est cet ordre qui aligne `ocr.json` et
`traduction.json`, et une inversion est **invisible** sur la page rendue. Les couleurs des
zones : bleu = normale, rouge = bulle vide, vert = réplique reprise à la main, orange =
sélectionnée.

| Outil | Ce qu'il fait |
|---|---|
| **Choisir** | sélectionner une bulle, sans rien modifier |
| **+ Rectangle** / **+ Ellipse** | tracer une bulle que la détection a manquée. L'ellipse est la forme d'un ballon : le nettoyage ne repeint pas les coins de la case |
| **Redessiner** | retracer la boîte de la bulle sélectionnée (son OCR et sa traduction repartent à zéro) |
| **Scinder** | tracer un trait au travers d'une bulle pour la couper en deux — le cas des deux ballons qui se touchent, pris pour un seul |
| **Supprimer la zone** | retirer une fausse détection |
| **Relire (OCR)** | relancer `manga-ocr` sur cette seule bulle. Ne traduit pas |
| **Retraduire** | un appel LLM court : une bulle, une réponse |
| **Garder ma version** | retient la réplique dans `traduction_manuelle.json` — le pipeline ne la réécrira jamais |
| **Vider, lire et traduire** | le geste complet sur une bulle ajoutée à la main : la zone est vidée dans la planche nettoyée, relue par l'OCR, puis traduite |
| **glisser un bloc de texte** | déplace la réplique et retient sa position dans `mise_en_page.json` |
| **double-clic sur une bulle** | met le curseur dans sa réplique — éditer là où l'on regarde |
| **Ctrl+Z / Ctrl+Y** | annuler · refaire |
| **Ctrl+S** | enregistrer **la planche** affichée |
| **Ctrl+Maj+S** | **enregistrer les modifications du projet** (cf. plus bas) |
| **Appliquer** | relance l'orchestrateur sur cette seule planche (relettrage, ou retraduction) |

Navigation : `Page préc.`/`Page suiv.` entre planches, `F` ajuster, molette zoomer, `Échap`
revenir à « Choisir », `Ctrl+J` afficher le journal. Le mémo complet est dans
**[COMMANDES.md](COMMANDES.fr.md)**.

**Au clavier, sans la souris.** Les flèches déplacent la zone sélectionnée d'un pixel (`Maj`
pour dix), `Ctrl`+flèches la retaillent. L'écriture part une demi-seconde après la dernière
touche, pas à chaque pression : un retaillage réécrit `regions.json`, `masks.png` **et** la
planche nettoyée. ⚠ **Tracer** une zone reste un geste de souris — ce n'est pas couvert.

**Thème clair ou sombre** — « Affichage → Thème ». Par défaut l'interface suit le réglage du
système, et le choix est retenu d'une session à l'autre dans `.angelith/interface.json`.
⚠ **Le canevas reste sombre dans les deux thèmes**, comme dans tout outil d'image : un fond
sombre autour d'une planche évite d'éblouir et fait ressortir le dessin. Les couleurs, les
tailles et les contrastes vivent tous dans `gui/theme.py` ; le tableau de contraste des deux
thèmes est publié dans
**[systeme-visuel-2026-08-27.md](mesures/systeme-visuel-2026-08-27.md)**.

⚠ **Rien n'est écrit avant `Ctrl+S`.** L'éditeur tient un document tamponné **par planche**,
avec son historique : on peut essayer, revenir en arrière, et ne valider qu'à la fin. Si un run
a retouché la planche entre-temps, l'écriture est **refusée** et la modification conservée.

⚠ **Plusieurs planches peuvent attendre en même temps.** Changer de planche ne demande plus
rien : chacune garde son document et ses saisies. Le titre porte un `*` tant qu'il reste du
travail non écrit **quelque part dans le tome**, et la ligne sous la barre d'outils dit où l'on
en est : `Planche 12 · 6 bulles · 2 corrigées · rendu périmé · 3 autre(s) planche(s) en attente`.

**« Enregistrer les modifications du projet » (`Ctrl+Maj+S`)** fait le geste complet : il écrit
toutes les planches en attente, relettre **les seules planches périmées**, et réassemble le
CBZ/PDF **une** fois. Un récapitulatif annonce d'abord lesquelles, pourquoi, et pour combien de
temps. Une planche refusée est nommée, son travail conservé, et n'arrête pas les autres.

⚠ **Fermer la fenêtre enregistre TOUTES les planches en attente**, et la boîte les nomme.
Jusqu'à la 1.6.0 elle n'en écrivait qu'une — la planche affichée — et jetait les autres sans
un mot : c'est le défaut que la 1.5.0 avait introduit en passant d'une planche ouverte à N.

⚠ **Un filet existe désormais contre le plantage.** Le travail non enregistré est recopié
toutes les 30 s dans `build/<…>/manga/.recuperation/`, et une reprise est proposée à la
réouverture du tome. Ce miroir vit **hors des checkpoints** et ne périme **aucun** rendu :
écrire les brouillons dans `traduction_manuelle.json` aurait fait passer une planche en « à
relettrer » à chaque caractère tapé, soit exactement le relettrage permanent que la 1.5.0
venait de supprimer. Un brouillon n'est pas un enregistrement.

**Chercher dans le tome.** Le champ au-dessus de la pellicule interroge les répliques, les
corrections manuelles et l'OCR japonais ; un clic sur un résultat ouvre la planche et met le
curseur dans la bulle. Sur `Entrée` et non à chaque touche : un balayage complet coûte
~210 ms sur 150 planches. Insensible à la casse et aux accents — mais **sur du latin
seulement** : le dakuten japonais est un signe combinant, et le retirer ferait trouver
« カキク » en cherchant « ガギグ ».

⚠ **L'éditeur travaille sur la planche NETTOYÉE**, avec un calque de texte par bulle — c'est ce
qui rend le déplacement possible. Ces calques sont produits par la fonction même du rendu
final : mesuré sur *manga A* Vol.1 planche 6, **0 pixel d'écart sur 1 800 000** avec la
page que le pipeline écrit. Un bouton bascule vers le rendu final pour comparer.

⚠ **Une zone ajoutée est VIDÉE dans la planche nettoyée.** Sans cela le lettrage écrirait le
français par-dessus le japonais — aucune étape de reprise ne relance le nettoyage. Symétrie :
supprimer une fausse détection restaure le dessin d'origine sous la zone retirée.

⚠ **Corriger une bulle ne coûte pas les autres.** Ajouter une zone sur une planche qui en
compte sept ne jette pas les six autres traductions : un appariement par IoU reporte OCR,
traduction **et corrections manuelles** sur les bulles restées les mêmes, y compris quand
l'ordre de lecture change. Seules les zones réellement nouvelles ou redessinées sont remises à
zéro, et l'interface dit lesquelles.

**Onglet « Runs » — le lanceur.** Manga *ou* light novel : projet, tome, étape de reprise,
planche unique, `--force`, `--dry-run`, `--verbose`, et les réglages de lot et de raisonnement.
Journal en direct, et un bouton **« Arrêter proprement »** qui écrit le même fichier `STOP`
que `--stop`.

**Le bandeau de run (lot 32).** L'avancement n'est plus une barre dans un onglet : c'est un
bandeau en pied de FENÊTRE, visible depuis n'importe quelle destination, qui nomme la phase
(« Traduction et rendu (5/6) »), l'objet en cours (`page_0084.png`, `lot 80→99`), l'avancement
compté (« planche 84 / 131 ») et le temps restant tiré du débit observé. Il ne recule jamais,
il **n'affiche aucun pourcentage**, et il passe en indéterminé — sans temps — dans les trois
cas où rien n'est comptable. Le titre de la fenêtre porte le même compte en tête, pour la
barre des tâches. Mesure : `docs/mesures/progression-2026-09-05.md`.

`perf.log` est écrit **dans tous les cas** (hors dry-run) depuis la 1.7.0 : la case « verbose »
ne décide plus que de ce qui s'affiche à l'écran, et les incidents (`⚠`) y atterrissent
quoi qu'il arrive. Avant, un run lancé sans elle ne laissait aucune trace fichier.

**Deux voies, et elles ne protègent pas la même chose.** La voie d'**écriture** est un fil
unique — c'est ce qui garantit qu'on n'écrit jamais deux fois le même checkpoint. La voie de
**lecture** compose les aperçus et les vignettes en parallèle, parce qu'elle ne fait que lire.
Les mêler coûtait cher à l'usage : l'aperçu de la planche 13 attendait derrière la retraduction
d'une bulle de la 12.

**Les planches sont préchargées.** Composer l'aperçu d'une planche coûte 1,37 s en médiane
(mesuré sur *manga A* Vol.1) et pèse 1,04 Mo ; la fenêtre de ±10 planches autour de celle
qu'on regarde est donc composée d'avance — ~21 Mo, ~27 s de fond — et passer à une voisine
prend alors **~200 ms, calques compris**. Réglable par `gui.apercu.fenetre` et
`gui.apercu.plafond_mo`.

**La pellicule ne gèle plus la fenêtre.** L'état d'une planche coûte 5,9 ms à calculer, et
l'interface le demandait 150 fois par geste — à l'ouverture, à chaque changement de filtre,
à chaque rafraîchissement : **888 ms** de fenêtre figée, ramenés à **31 ms** par un cache
invalidé par les `mtime` déjà lus. Vérifier la fraîcheur ne coûte que 1 % du prix de la
réponse (13 ms de `stat` contre 1 095 ms de parsing JSON) — c'est ce rapport, mesuré avant
d'écrire le cache, qui le justifie.

**Le verrou ne couvre plus que ce qui écrit.** Pendant « Enregistrer le projet », la
pellicule, la navigation, le zoom et la lecture restent vivants : seuls les boutons qui
écrivent grisent. Lire ne risque rien, et griser le panneau entier pendant plusieurs minutes
était une gêne pure. La bascule 🔒 garde en plus le cadrage d'une planche à l'autre — sans
elle, comparer la même zone sur deux planches consécutives obligeait à rezoomer à chaque fois.

**La pellicule remplace la liste.** Une vignette par planche, avec ses pastilles : `⟳` rendu
périmé, `✎n` répliques corrigées à la main, `↔n` textes déplacés, `⚠n` débordements, `∅` aucune
détection. Un filtre isole *modifiées à la main · rendu périmé · débordements · sans traduction
· jamais rendues* — les mêmes planches que celles que « Enregistrer le projet » relettrera. Les
vignettes vivent en cache disque et se repériment dès qu'un relettrage réécrit la planche.

**La bande se remplit en trois temps**, et c'est l'ordre qui compte : la planche **regardée**
d'abord, entièrement ; puis **toutes** les vignettes, qui coûtent quelques dizaines de
millisecondes pièce ; puis seulement les aperçus des planches voisines, à 1,37 s l'unité. Ces
deux travaux étaient triés ensemble par simple proximité, si bien que les 21 aperçus de la
fenêtre passaient devant toutes les vignettes — une trentaine de secondes pendant lesquelles
la bande restait vide au-delà du voisinage immédiat. Une planche pas encore miniaturisée
affiche un cadre d'attente à la taille exacte de sa cellule : rien ne bouge quand l'image
arrive à sa place.

Une seconde demande sur une planche occupée est
mise en file plutôt que refusée. Les modèles (détecteur, OCR, agents, glossaire) restent chauds
pour toute la session.

**Ce que l'interface ne fait pas, délibérément :**

- **aucun chemin de traitement qui lui soit propre.** Elle appelle `process_volume`, écrit par
  `manga/edition.py`, et relettre par `--page N --from rendu`. Un tome retouché à l'écran se
  relance à l'identique avec `run_manga.py`, et réciproquement ;
- **elle ne réécrit jamais `config.yaml`** — ses commentaires sont sa documentation. Le menu
  *Fichier* propose de l'ouvrir dans l'éditeur système ;
- **elle ne dessine rien sur la planche** : le principe « l'IA ne dessine jamais » vaut aussi
  pour l'utilisateur. On édite des zones et du texte ; nettoyage et lettrage restent
  déterministes ;
- **un seul run à la fois**, et l'édition est suspendue pendant.

Si un run a modifié la planche pendant qu'elle était à l'écran, l'écriture est **refusée** avec
proposition de recharger : `projet.json` porte une révision qui n'augmente que si le contenu
change.

### Corriger une réplique à la main

Crée `build/<Projet>/<Tome>/manga/.checkpoints/page_XXXX/traduction_manuelle.json` :

```json
{ "0": "Ma version de la première bulle", "3": "" }
```

L'index est celui de la bulle dans l'ordre de lecture (0 pour la première), tel qu'il apparaît
dans `qa.json` et `traduction.json`. Une chaîne vide est une décision éditoriale valable — une
bulle de silence. Un index hors bornes est ignoré plutôt que de décaler la planche.

Ce fichier n'est produit par aucune étape : il est **lu** et superposé après la traduction,
avant le forçage et le rendu. C'est ce qui rend un re-run non destructif.

`python gui.py` l'écrit aussi pour toi (bouton **« Garder ma version »**) — le format ne change
pas, et les deux voies restent interchangeables.

### Limites connues (honnêtes)
- **Le texte hors bulle est détecté et traduit, mais JAMAIS effacé** (depuis la v0.40.0).
  Onomatopées et narration posées sur le dessin sont trouvées, lues, traduites — et **listées
  dans `RAPPORT.md`**. Le japonais d'origine reste visible et intact : l'effacer demanderait
  de reconstruire le dessin, donc un modèle génératif, ce qu'interdit le principe « l'IA ne
  dessine jamais » (§ *Principe* ci-dessus).

  ⚠ **La détection est fiable, la LECTURE ne l'est pas.** `manga-ocr` est un modèle de
  *dialogue* : il rend toujours une phrase japonaise plausible, donc sur une onomatopée
  stylisée il **invente**. Mesuré sur le Vol.2 : la colonne `ゴォォォ` de la page 63 est lue
  `うんなんじゃないか`. Sur du **texte libre** (narration, pensée hors bulle) en revanche, la
  chaîne fonctionne — page 25, `ああ．．．陽弥．．．` → « Ah... Haruya... ».

  D'où le défaut `manga.onomatopees.mode: "rapport"` : **rien n'est dessiné sur la planche**.
  Les lectures et leurs traductions apparaissent au rapport sous un titre « À RELIRE », prêtes
  à servir pour lettrer à la main dans Photoshop.

  `mode: "glose"` dessine en plus la traduction à côté du japonais. Le **placement** est sûr
  (une glose ne recouvre jamais l'encre, ni une bulle, ni une autre glose — invariant testé) ;
  c'est le **contenu** qui ne l'est pas encore. `actif: false` désactive entièrement la passe.

  ⚠ Le modèle utilisé (`comic-text-detector`) est sous **GPL-3.0**, avec des poids entraînés
  pour partie sur **Manga109-s**. Vérifie ces licences avant de diffuser les planches
  produites — même vigilance que pour les polices.
- **La détection peut se tromper** (faux positifs sur des formes qui ressemblent à une
  bulle). Une fausse détection sur du dessin est désormais **détectée et laissée
  intacte** : en dessous de `manga.nettoyage.seuil_abandon`, l'intérieur n'est pas uni,
  donc ce n'est pas une bulle — on n'y touche pas et le rapport la signale. Sur le tome
  de référence, 2 détections sur 797 (un gratte-ciel et une trame). Elles gardent leur
  texte japonais, visible donc corrigible ; ajuste `manga.detection.conf_threshold` si
  elles sont nombreuses.

  Pour une planche isolée, on peut **relancer la détection à d'autres seuils** — après avoir
  vu ce que ça donnerait, car baisser `conf` fait toujours apparaître des régions et la
  question est lesquelles :
  ```
  python tools/apercu_detection.py "Mon Manga" Vol.1 --page 44 --balayage
  python run_manga.py "Mon Manga" Vol.1 --page 44 --conf 0.45
  ```
  L'aperçu n'écrit rien et ne coûte **qu'une inférence** quel que soit le nombre de réglages
  essayés : les seuils ne servent qu'au post-traitement, le réseau ne les voit jamais.
  `--vignette` en donne une version annotée (bleu = conservée, vert = gagnée, rouge = perdue).

  La relance, elle, n'écrit que si un **arbitre** l'accepte : « mieux » n'est jamais « plus de
  bulles ». Il oppose son véto si une vraie bulle disparaît, si une bulle gagnée serait refusée
  par le nettoyage, si deux masques se recouvrent ou si le nombre de bulles explose — et il
  accepte l'inverse, écarter une région que le nettoyeur refusait déjà de nettoyer. Le doute
  profite toujours à la détection en place : elle a déjà été payée en OCR et en traduction.
  `--conf`/`--iou` exigent `--page` (un seuil de tome appartient à `config.yaml`) et impliquent
  `--from detection`.
- **Bulles doubles : une région pour deux ballons.** Le détecteur émet parfois **une**
  instance là où le dessinateur a mis **deux** ballons qui se touchent — 5 régions pour
  6 ballons page 136 du tome de référence, 8 pour 9 page 142. Les deux répliques étaient
  alors lues en une seule chaîne (`敵機２時方向！いいよ転校生！！`, deux locuteurs),
  traduites en une, et composées **sur le goulot entre les lobes** : 13 px là où les autres
  bulles de la planche sont à 17-31 px. Rien ne le signalait — autant de traductions que de
  bulles, et le texte tenait.

  Depuis le lot 4.2, ces régions sont **scindées** avant l'OCR
  (`manga/bubbles_split.py`) : chaque ballon reçoit son texte, sa taille et sa place. Le
  réglage est volontairement conservateur (scinder à tort casserait une planche correcte),
  et il reste donc des doubles non scindés — listés dans `RAPPORT.md` sous « Régions
  bi-lobées SUSPECTES ». Pour voir la distribution complète :
  ```
  python tools/mesurer_bulles.py "Mon Manga" Vol.1
  python tools/mesurer_bulles.py "Mon Manga" Vol.1 --scindables   # sans rien écrire
  python tools/banc.py --tous                    # les mêmes chiffres, TOUS les volumes
  python tools/banc.py --tous --markdown         # …daté, avec commit et empreinte de config
  ```
  ⚠ Un tome déjà traité **migre tout seul** au premier run suivant, sans le modèle ONNX (la
  scission travaille sur les masques en cache). Mais une planche qui gagne des bulles perd
  son OCR et sa traduction : l'alignement par position est irrécupérable, et la chaîne
  fusionnée était fausse. Sur le tome de référence : **18 planches sur 150** à re-OCRiser et
  re-traduire, les 132 autres gardent tout.
- **Le texte ne peut pas déborder d'une bulle** : il est composé dans le masque (profil de
  largeur mesuré ligne par ligne) puis découpé à l'intérieur. Quand une réplique ne peut
  vraiment pas tenir — un mot insécable plus large que la bulle — elle est dessinée à la
  taille minimale et **signalée** dans `RAPPORT.md`, jamais tronquée ni résolue en
  agrandissant la bulle. Le bon correctif est de raccourcir la traduction.
- **VRAM (20 Go et moins)** : par défaut la détection tourne sur CPU (pas de
  contention avec le LLM). Si tu actives `DmlExecutionProvider` (GPU AMD/Windows via
  DirectML), le LLM est automatiquement déchargé une fois avant la détection/OCR
  (il se recharge tout seul à la 1ère traduction) pour éviter le cumul CV+LLM sur le
  même GPU.
- **Ordre de lecture des bulles** : coupe X-Y récursive sur les boîtes (plus grande
  gouttière horizontale contre verticale, en écart normalisé ; horizontale → haut puis bas,
  verticale → **droite puis gauche**). C'est *panel-aware sans jamais détecter les cases* :
  les gouttières entre cases sont les gouttières entre groupes de bulles. Une mise en page
  très libre (bulles se chevauchant sur les deux axes) retombe sur un tri diagonal et peut
  demander un réordonnancement manuel.
- **Changer l'ordre de lecture invalide le format du cache** : `regions.json` porte un
  `format`, et `ocr.json`/`traduction.json` s'alignent **par position** sur l'ordre. Le
  passage à la coupe X-Y est donc migré automatiquement au premier run — les régions sont
  réordonnées et les textes suivent la même permutation, sans rien recalculer.

---

## 13. Sources en images — OCR d'un LN japonais scanné

> Mémo des commandes de cette brique : **[COMMANDES.md](COMMANDES.fr.md)**.

Un light novel arrive parfois en **scans** : `sources/<Projet>/<Tome>/JAP/*.jpg`, pas de
`.docx` ni d'`.epub`. `pipeline/sources.py` ne retenant que `.docx|.pdf|.epub|.txt|.md`, le
tome s'arrêtait sur « Aucune source exploitable ». La brique `scan/` produit le `.md` qui
manque, et **le pipeline LN n'a pas été modifié pour autant** : il lit un `.md` comme il l'a
toujours fait.

```powershell
pip install -r requirements-scan.txt      # sous-ensemble de requirements-manga.txt
python run_ocr.py --check

python run_ocr.py "Mon LN" Vol.1          # ~2 h pour 270 pages, reprise possible
python run.py     "Mon LN" Vol.1          # inchangé
```

### La contrainte qui décide de tout

`manga-ocr` redimensionne son entrée en 224 × 224. Mesuré sur une page réelle de 2 452 ×
3 543 px, une **colonne entière** de ~40 caractères (2 733 px de haut) en ressort *inventée* :
23 à 29 caractères rendus, sans rapport avec la page. Les mêmes pixels **découpés en tranches
de 8 à 16 caractères** sont lus correctement à ~95 %.

Toute la brique existe donc pour répondre à une seule question — *où couper ?* — et elle y
répond **sans le moindre modèle**, parce qu'une page de roman imprimé est une grille
régulière. C'est le raisonnement que `manga/ocr.py` tient déjà pour l'ordre de lecture.

### Ce que l'analyse mesure

| | Comment | Pourquoi pas autrement |
|---|---|---|
| **Binarisation** | balayage de 6 seuils, on garde celui qui donne la grille la plus régulière | l'écart entre le bon seuil et le mauvais n'est pas un compromis mais une falaise : à 128 la page sort en **une seule bande**, à 112 en 16 colonnes. Otsu place le seuil à ~195 — bien au-delà de la falaise |
| **Colonnes** | projection verticale, puis fusion relative | un `「` ou un `ー` coupe sa propre bande : 41 bandes brutes pour 16 colonnes réelles |
| **Ruby** | bande étroite collée à droite d'une colonne | mêlées au crop, elles se lisent en alternance avec le texte et détruisent la ligne |
| **Numéro de page** | hors marge, *ou* fragment court isolé par une large gouttière | sur une page paire il se pose **au-dessus d'une colonne**, dans les mêmes abscisses : la règle de marge ne voit rien |
| **Paragraphes** | indentation (mode des débuts de colonne) **ou** crochet ouvrant | une réplique japonaise n'est pas indentée — le crochet occupe le retrait, et seule la règle typographique la voit |
| **Coupes** | position proportionnelle, affinée sur une gouttière **large** | couper dans un blanc intra-glyphe donne un demi-signe à chaque tranche, et le modèle en invente un entier de part et d'autre |

### Le garde-fou est gratuit

La grille sait combien de caractères une colonne contient ; l'OCR rend une chaîne. Comparer
les deux ne coûte rien et attrape exactement le mode d'échec ci-dessus. Une colonne qui
s'écarte de plus de 25 % est **relue une fois, avec un découpage décalé** — rejouer le même
découpage redonnerait la même hallucination, le modèle étant déterministe. Ce qui reste
douteux est nommé, page par page, en tête de `RAPPORT.md`.

### Illustrations, titres, furigana

- Une page sans grille exploitable (couleur, trop encrée, moins de 4 colonnes) est une
  **illustration** : elle est copiée dans `<langue>/media/` et remplacée par
  `<!-- IMG: media/page_0010.jpg -->`, le marqueur que `extract.py` produit déjà pour les
  `.docx`/`.epub`. Elle ressort donc **à sa place** dans le DOCX/EPUB/PDF final.
- Une page à gros corps tenant en 3 colonnes est un **titre** : elle sort en `# …`, ce qui
  suffit à `pipeline/split.py` (`第N話` est déjà dans ses motifs par défaut).
- Les **furigana** sont ignorés par défaut, comme pour l'EPUB et pour la même raison mesurée
  (ils gonflent le japonais transmis au traducteur d'environ 30 %). `scan.ruby: parentheses`
  les rend en `唖然(あぜん)`, à un caractère près sur la position.

### Régler, puis lancer

L'aperçu ne charge aucun modèle et coûte ~0,1 s : c'est par lui qu'il faut passer avant de
payer deux heures d'OCR sur un tirage inhabituel.

```powershell
python run_ocr.py "Mon LN" Vol.1 --page 100 --apercu    # colonnes, coupes, ruby, mobilier
python run_ocr.py "Mon LN" Vol.1 --page 100 --verbose   # la page, texte compris
python run_ocr.py "Mon LN" Vol.1 --from lecture         # étapes : analyse, lecture
python run_ocr.py "Mon LN" Vol.1 --stop                 # dans un AUTRE terminal
```

Le cache est **par page** : une interruption ne reperd rien, et relancer la même commande ne
relit aucune page déjà faite. L'unité d'arrêt est la page.

### Limites, franchement

- **~2 h par tome de 270 pages** sur processeur (0,5 s/tranche, ~30 s/page). Un `torch` CUDA
  change l'ordre de grandeur ; le lot de 16 ne gagne que 30 %, le décodage autorégressif
  dominant.
- **Le nombre de cases prédit est approché** (~7 % de biais : le pas mesure la largeur
  d'encre, pas l'avance typographique). J'ai cherché à retrouver l'avance réelle en ajustant
  les hauteurs de colonnes sur des multiples entiers ; le résidu est à peine meilleur que le
  hasard. Le seuil de suspicion est donc large et assumé plutôt que calibré à faux.
- **Le `.md` est écrit dans `sources/`**, seule écriture du dépôt à cet endroit. C'est
  délibéré : c'est le seul endroit où `pipeline/sources.py` regarde, le fichier se corrige à
  la main, et il survit à un vidage de `build/` — ce qui n'est pas un détail quand il
  représente deux heures d'OCR.
- **Relis `RAPPORT.md` avant de traduire.** Personne ne vérifiera 270 pages de japonais
  vertical à l'œil ; c'est tout l'objet du garde-fou et du classement par doute.
