# PLAN 23 — La bible visuelle : savoir à quoi ressemble un personnage avant de prétendre le dessiner

> **Lire `00-CONTEXTE-AGENT.md` puis `README-ILLUSTRATION-23-27.md` d'abord.**
>
> **Nature attendue** — **MINEUR**. Nouveau fichier de données, nouveau module, nouvel outil, aucun
> changement du chemin nominal, aucune clé de `config.yaml` armée par défaut.
>
> **Charge estimée** — 12 jours (10 + 2 pour L23.7, la signature de style, ajoutée le 2026-08-27).
>
> **Ce lot ne génère AUCUNE image.** Il n'importe aucun modèle génératif, il n'ajoute aucune
> dépendance lourde, et il ne touche pas au principe directeur. Il a sa valeur propre : même si les
> `PLAN-24` à `27` n'étaient jamais exécutés, il resterait un gain de **qualité de traduction**.
>
> **Prérequis** — aucun.

---

## 1. Le constat, et il est mesuré

Le dépôt traduit des œuvres depuis des mois et ne sait **rien** de l'apparence de ses personnages.
Mesure du 2026-08-27 sur les `sources/*/glossaire.yaml` vivants :

| Mesure | Valeur | Dénominateur |
|---|---|---|
| Projets portant un `glossaire.yaml` vivant | **5** | 17 projets sous `sources/` |
| Personnages déclarés | **171** | ces 5 projets |
| `role` vide | **171** | 171 — soit **100 %** |
| `genre: '?'` ou vide | **150** | 171 — soit **87,7 %** |
| `description` vide | **0** | 171 |

Détail par projet, parce qu'un total masque une distribution : `manga D` 119 personnages
dont **119** sans genre ; `roman O` 27 dont **27** ; `roman S` 24 dont **4** ;
`webtoon A` 1 dont 0 ; `Pride and Prejudice` 0 personnage déclaré.

**Deux lectures de ces chiffres, et les deux comptent.**

1. `core/glossary.py:ENTITY_CATS` étiquette la catégorie « Personnages (**le genre commande les
   accords**) ». Le genre n'est pas décoratif : c'est lui qui décide de « elle est arrivée » contre
   « il est arrivé » en français. **87,7 % des personnages ne le portent pas.** Le terminologue
   remplit `description` (0 vide sur 171 — il fait son travail) et ne remplit ni `genre` ni `role`.
2. Les `description` existantes sont **narratives, pas visuelles**. Exemple réel, `roman S` :
   « Fille de l'orphelinat Noelle, sujet principal du journal ; sourire déchirant. » ; « Commandant
   de peloton surnommé « as », réputé pour charger l'ennemi en première ligne. » Rien sur la
   couleur des cheveux, l'âge apparent, la tenue. Un modèle d'image n'en tire rien.

Et pourtant le matériau existe : **404 fichiers dans 13 dossiers `build/*/*/media/`**, dont 164
pour le seul `Pride and Prejudice` Vol.1 et 1 pour `Demo LN` → **239 illustrations sur 11 tomes de
10 œuvres**. `pipeline/images.py` connaît déjà leur **position** dans le chapitre
(`manifest_for_chapter` rend `[(fraction, contenu_marqueur)]`), et `core/llm.py` sait déjà **envoyer
une image au LLM** (`LLM.chat(..., images=[b64])`, l. 180-202, base64 sans préfixe, modèle
`yume-27b` annoncé vision-capable).

**Personne n'a jamais relié les trois.** C'est ce lot.

---

## 2. Étape 0 — mesurer avant d'écrire une ligne

Publiez le tableau de chaque sous-étape et **arrêtez-vous**. Alexandre relit avant tout code.

### 0.1 — Le compte honnête des illustrations

Le chiffre de 404 vient d'un `ls` : il compte tout ce qui traîne dans `media/`, y compris les
couvertures, les logos d'éditeur, les bandeaux de série et les vignettes de quatrième de couverture.
Reclassez-les **déterministement**, sans modèle :

| Classe | Critère proposé (à ajuster sur la mesure, pas sur l'intuition) |
|---|---|
| couverture | premier marqueur du volume, ou ratio proche du ratio de page et surface maximale du tome |
| pleine page | surface ≥ 60 % de la médiane des surfaces du tome, ratio portrait |
| double page | ratio paysage > 1,3 |
| vignette / logo | surface ≤ 10 % de la médiane, ou moins de 3 couleurs distinctes dominantes |
| indéterminé | tout le reste — et cette classe doit être **généreuse** |

**Publiez la répartition des 404 fichiers dans ces cinq classes, par tome.** C'est ce chiffre, et
non 404, qui dit combien de références exploitables existent réellement.

⚠ **`Pride and Prejudice` Vol.1 pèse 164 des 404 fichiers, soit 40,6 %.** Une moyenne calculée sur
les 13 dossiers sans le dire est fausse. Donnez toujours les deux : avec et sans.

### 0.2 — Combien d'illustrations sont rattachables à un chapitre ?

`pipeline/images.py:manifest_for_chapter` donne la position fractionnaire de chaque marqueur
`<!-- IMG: chemin -->` dans son chapitre ; `orphan_markers` donne ceux qui ne sont dans aucun
chapitre — et la docstring de ce fichier porte déjà une mesure utile : sur un volume,
« 12 illustrations sur 20 perdues » avant le correctif, parce que les planches couleur de tête de
volume précèdent la première frontière de chapitre.

**Mesurez, par tome : combien d'illustrations sont positionnées dans un chapitre, combien sont
orphelines.** Une orpheline (planche couleur de tête) est souvent la **meilleure** référence
visuelle du tome : ne la jetez pas, marquez-la `contexte: tete_de_volume`.

### 0.3 — Le LLM vision voit-il quelque chose ?

Sur **12 illustrations** tirées de deux tomes (dont au moins 4 de `Pride and Prejudice`), demandez à
`yume-27b` par `LLM.chat(..., images=[b64])` de décrire **ce qu'il voit**, sans lui donner le
glossaire : combien de personnes, leurs attributs visibles, le cadre.

Publiez, à la main, une colonne « exact / partiel / faux » et **le compte de descriptions
inutilisables**. Deux résultats possibles et les deux sont des résultats :

- si le modèle décrit correctement ≥ 8 des 12, l'étape L23.3 est faisable ;
- s'il en décrit moins de 6, **écrivez-le et arrêtez L23.3** : le lot se réduit à L23.1, L23.2 et
  L23.6, il vaut toujours ses jours, et la bible se remplit à la main dans l'interface.

⚠ `ETAT_BRIQUES` et le `README` annoncent `yume-27b` « vision-capable ». **Vérifiez-le** par
`ollama show <modèle>` et citez la sortie : le dépôt a déjà eu quatre affirmations fausses sur
lui-même (`docs/mesures/webtoon-2026-08-26.md`).

---

## L23.1 — Le classement des illustrations, dans `core/` et sans Qt

Nouveau module **`core/illustrations.py`** — pas dans `pipeline/`, parce que la brique manga en aura
besoin aussi, et pas dans `gui/` (règle de couche du `00-CONTEXTE-AGENT.md` §8) :

- `inventaire(tome: Path) -> list[Illustration]` — parcourt `build/<Projet>/<Tome>/media/`, lit
  taille et dimensions avec Pillow (déjà dépendance), sans charger l'image entière quand
  `Image.open` suffit à donner `.size` ;
- `classer(illus, mediane_surface) -> str` — la table de l'étape 0.1, **pure, testable, sans
  disque** ;
- `rattacher(tome) -> dict[str, list[Illustration]]` — croise avec les marqueurs via
  `pipeline.images.manifest_for_chapter`, en réutilisant l'existant : **n'écrivez pas un second
  parseur de marqueurs**, `_MARKER_RE` est déjà là.

Tests : `tests/test_illustrations.py`, avec des images synthétiques fabriquées par Pillow dans un
`tmp_path` — pas de fixture qui dépende de `build/`.

## L23.2 — `bible.yaml`, et surtout PAS dans `glossaire.yaml`

**La bible est un fichier séparé : `sources/<Projet>/bible.yaml`.**

⚠ **Trois raisons, et la première est un interdit.** L'interdit n° 1 du `00-CONTEXTE-AGENT.md` et la
règle MAJEUR du `CHANGELOG` disent la même chose : *un changement du schéma `glossaire.yaml` qui
invalide les caches est un MAJEUR*, et une relance de tome coûte des heures de GPU. Ajouter un champ
`apparence` dans `FIELD_ORDER["personnages"]` ferait passer tout le glossaire dans
`glossary.to_text()` → dans le prompt du traducteur → **changement du caractère de la traduction**,
donc de la sortie de tous les tomes. Deuxièmement, `core/glossary.py:save` réécrit le fichier avec
ses bannières et son ordre canonique : un champ de plus, c'est un diff sur les 171 entrées de
chaque projet. Troisièmement, la bible contient des **chemins d'images** et des recadrages : ce
n'est pas de la terminologie.

Schéma proposé, aligné sur le style du glossaire (tous les champs écrits, même vides) :

```yaml
# bible.yaml — référentiel VISUEL de l'œuvre. Alimente l'atelier d'illustration.
# N'entre JAMAIS dans le prompt du traducteur. Ne remplace pas glossaire.yaml.
version: 1

# ── STYLE DE L'ŒUVRE ── ce qui empêche une image générée d'être « juste » et pourtant étrangère
# au tome. Alimenté par L23.7. Sans ce bloc, l'atelier ne sait reproduire qu'un personnage,
# pas un registre graphique.
style:
  ancrages:                     # 2 à 5 images REPRÉSENTATIVES du registre du tome
  - fichier: 'media/…_p1_x226.jpeg'
    classe: 'tete_de_volume'
    motif: 'planche couleur, palette et trait de référence'
    valide_par_humain: false
  signature:                    # MESURÉE par L23.7, jamais saisie à la main
    palette: []                 # couleurs dominantes, hex
    saturation_moyenne: null
    contraste: null
    densite_trait: null         # part de pixels de contour
    part_aplats: null           # part de pixels en zones uniformes
    couleur: null               # true = couleur, false = niveaux de gris
    echantillon: null           # SUR COMBIEN d'images — un chiffre sans dénominateur n'est rien
  mots: ''                      # description LLM, VALIDÉE à la main, jamais utilisée seule

personnages:
- nom: Tory Noelle              # DOIT correspondre à cibles.fr.nom du glossaire
  genre_confirme: ''            # '', 'féminin', 'masculin' — voir L23.5
  source_genre: ''              # 'illustration', 'texte', 'humain'
  apparence:
    cheveux: ''
    yeux: ''
    age_apparent: ''
    tenue: ''
    signes: []                  # cicatrice, lunettes, uniforme…
  citations:                    # CHAQUE attribut vient d'une phrase, ou n'existe pas
  - attribut: cheveux
    texte: "…"
    source: 'chapters/ch03.md'
  references:
  - fichier: 'media/…_p12_x298.jpeg'
    classe: 'pleine_page'
    contexte: 'ch03@0.42'
    confiance: 'humaine'        # 'humaine' | 'llm' | 'proposee'
    recadrage: [x, y, w, h]
    role: 'identite'            # 'identite' | 'style' — deux usages, deux canaux (PLAN-26 L26.0)
  valide_par_humain: false
```

`core/bible.py` : `load(projet)`, `save(bible, projet)`, `fill_defaults`, `verifier_coherence`
(tout `nom` doit exister dans le glossaire ; toute `references[].fichier` doit exister sur le
disque). Réutilisez le patron de `core/glossary.py` — même politique de fusion **sans écrasement**
d'un champ rempli à la main, même écriture de tous les champs.

⚠ **La bible reste sous `sources/`, qui est exclu en bloc par `.gitignore`** avec cette raison
écrite : « l'arbre git exposait alors le NOM de chaque œuvre comme nom de dossier ». Ne la déplacez
pas, ne l'écrivez pas ailleurs, ne créez pas de dossier `bibles/` à la racine.

## L23.3 — L'attribution par le LLM vision, avec l'abstention comme comportement normal

Ne faites cette étape que si l'étape 0.3 l'autorise.

Pour chaque illustration classée `pleine_page`, `double_page` ou `tete_de_volume` : un appel
`LLM.chat` avec l'image **et** la liste des personnages du glossaire (nom + description narrative +
genre déclaré), qui demande une sortie stricte :

```
personnages_visibles: [<nom du glossaire>, …]   # vide si aucun
attributs: {<nom>: {cheveux, yeux, age_apparent, tenue, signes}}
certitude: haute | moyenne | indeterminee
```

**Trois garde-fous, tous déjà dans la culture du dépôt :**

1. **La classe « indéterminée » est généreuse**, comme le classifieur de type de bulle du
   `PLAN-17`. Une attribution moyenne écrite dans la bible sans relecture est pire qu'une case vide :
   elle se propagera dans toutes les images générées du personnage.
2. **Un nom hors glossaire est rejeté**, pas ajouté. Le glossaire reste la source unique des noms.
3. **Aucune écriture directe.** Le LLM produit un fichier `sources/<Projet>/bible.propositions.yaml`
   avec `confiance: 'llm'`. Seule L23.5 le fait entrer dans `bible.yaml`.

Coût : un appel vision par illustration retenue. Sur les 239 illustrations non-domaine-public, si
30 % sont retenues, c'est ~70 appels par corpus complet, une fois. Mesurez le temps réel sur un
tome et écrivez-le : c'est ce chiffre qui dit si l'étape est utilisable ou pas.

## L23.4 — Les attributs qui viennent du TEXTE, et qui citent leur phrase

Le texte traduit est sous `build/<Projet>/<Tome>/chapters/*.md` — du français propre, déjà découpé.

Pour chaque personnage, cherchez les passages qui portent un attribut visuel. **Deux passes, dans
cet ordre, et la première est déterministe :**

1. **Lexique** : une liste de tête de phrase (« cheveux », « yeux », « chevelure », « uniforme »,
   « cicatrice », « lunettes », « silhouette »…) croisée avec le nom du personnage et ses
   `variantes` du glossaire, dans une fenêtre de N phrases. Aucun modèle. C'est ce qui donne le
   **dénominateur** : combien de personnages ont au moins un passage candidat.
2. **LLM** sur les seuls passages candidats, pour en extraire l'attribut normalisé.

**Règle non négociable : un attribut sans `citations[]` n'entre pas dans la bible.** C'est la même
règle que la règle des chiffres du §5 du `00-CONTEXTE-AGENT.md`, transposée : *un attribut sans sa
phrase source n'est pas une observation, c'est une invention*. Et c'est exactement ce qui distingue
« illustration cohérente avec l'œuvre » de « illustration plausible ».

Le prompt de cette passe est un **fichier de prompt**, `langues/fr/prompts/bible_apparence.md`, avec
l'en-tête de licence **à la fin** (interdit n° 6). ⚠ **Ne l'ajoutez PAS à `core/langues.py:PROMPTS_REQUIS`.** Ce tuple ne porte que les **huit**
prompts sans lesquels un tome sortirait partiellement dans une autre langue, et `_verifier_prompts`
**refuse** un pack auquel il en manque un — y ajouter un nom rendrait le pack `langues/en` invalide
du jour au lendemain. Le précédent exact existe déjà : `manga_relecteur.md` est livré dans les deux
packs et **absent** de `PROMPTS_REQUIS`. Suivez-le, et traitez l'absence du fichier comme un refus
explicite de la brique — pas comme un repli sur le français : « aucun repli silencieux » est la
règle écrite de ce module.

## L23.5 — La validation humaine, et le genre qu'on gagne au passage

Un outil en ligne de commande, `tools/bible.py`, avant toute interface :

```powershell
python tools/bible.py "<Projet>" --inventaire        # L23.1, tableau des classes
python tools/bible.py "<Projet>" --proposer          # L23.3 + L23.4 → bible.propositions.yaml
python tools/bible.py "<Projet>" --revue             # passe en revue et écrit bible.yaml
python tools/bible.py "<Projet>" --rapport --markdown > docs/bible-<Projet>-<date>.md
```

`--revue` présente, personnage par personnage : les attributs proposés avec leur citation, les
illustrations candidates avec leur chemin, et attend `o/n/?`. Ce qui est accepté passe en
`confiance: 'humaine'` et `valide_par_humain: true`.

**Le gain qui justifie ce lot à lui seul :** quand une illustration ou une citation lève le genre
d'un personnage, `--revue` propose d'écrire `genre` **dans le glossaire** — c'est-à-dire dans le
seul champ que le traducteur lit déjà, et qui commande les accords français. **150 personnages sur
171** sont concernés.

⚠ **Écrire `genre` dans `glossaire.yaml` n'est PAS un changement de schéma** — le champ existe, il
est vide. Mais c'est un **changement de sortie** : les accords d'un tome relancé changeront. Donc :
opt-in explicite (`--ecrire-genre`), jamais en défaut, et l'entrée de CHANGELOG doit le dire en
tête. Vérifiez également l'interaction avec `core/glossary_force.py` et
`langues.appliquer_traductions_forcees` avant de toucher au fichier.

## L23.6 — Le banc de la bible

`tools/bible.py --rapport` produit, par projet :

| Indicateur | Ce qu'il mesure |
|---|---|
| couverture de référence | personnages avec ≥ 1 `references[]` **validée par un humain** / personnages du glossaire |
| couverture d'attributs | personnages avec ≥ 3 attributs cités / idem |
| genre résolu | avant / après ce lot, sur les 150 |
| illustrations exploitées | retenues / 404, et le détail par classe |
| abstentions du LLM | `indeterminee` / appels — **publiez-le**, une abstention basse est suspecte |

Le document `docs/bible-visuelle-<date>.md` porte la date, le commit et l'empreinte SHA-256 de
`config.yaml`, comme le produit déjà `tools/banc.py --markdown`, et **reprend les critères ci-dessous
un par un, y compris les non tenus**.

---

## L23.7 — La signature de style du tome, et elle se mesure

**C'est l'étape qui répond à « ne pas produire un résultat trop loin des images précédentes ».**
Un personnage fidèle dessiné dans un registre étranger — rendu 3D, photographie, aquarelle — est un
échec que ni le genre, ni les attributs, ni les recadrages n'attrapent.

Elle est **entièrement déterministe**, en numpy et Pillow, sur les illustrations classées
`pleine_page`, `double_page` et `tete_de_volume` du tome :

| Descripteur | Comment | Pourquoi lui |
|---|---|---|
| palette dominante | quantification des couleurs, N teintes et leur poids | c'est le premier écart visible d'une génération |
| saturation moyenne, contraste | statistiques sur HSV / luminance | sépare un tome pastel d'un tome contrasté |
| densité de trait | part de pixels de contour (gradient au-dessus d'un seuil relatif) | trait fin contre trait épais |
| part d'aplats | part de pixels en zones uniformes — la même notion que l'**uniformité de fond** déjà calibrée par `manga/clean.py` sur 797 bulles, médiane 0,892 | aplats contre dégradés |
| couleur ou niveaux de gris | variance des canaux | une planche N&B et une planche couleur ne se comparent pas |

⚠ **Trois règles, et la deuxième est la règle des chiffres du dépôt.**

1. **Aucun seuil absolu.** Comme partout dans ce dépôt, les descripteurs sont **relatifs au tome** :
   la signature est une référence interne, pas une norme. C'est déjà la doctrine de la brique scan,
   dont « les seuils, quoique tous relatifs et non absolus, n'ont pas encore vu d'autre imprimeur ».
2. **`echantillon` est obligatoire.** Une signature calculée sur 3 images et une sur 30 ne valent pas
   la même chose ; le champ porte le dénominateur, sinon la signature est une impression.
3. **Les ancrages sont validés à la main.** Le déterministe propose les plus représentatives (les
   plus proches du centre de la distribution des descripteurs) ; l'humain confirme. Une couverture
   avec un logo d'éditeur et un bandeau de prix est une mauvaise ancre, et aucun descripteur ne le
   sait.

**Publiez, par tome : la signature, son échantillon, et l'écart entre les deux tomes d'une même
œuvre.** Si deux tomes de la même série ont des signatures très écartées, c'est un fait important —
il veut dire qu'une signature « par œuvre » n'a pas de sens et qu'il faut la faire par tome.

⚠ **Ce lot ne fait rien de cette signature** : il la mesure et l'écrit. C'est `PLAN-25` étape 0.2 qui
lui donne une échelle, et `PLAN-26` L26.0 qui la consomme.

## 3. Les critères de ce lot

1. `core/illustrations.py` classe les **404** fichiers des 13 dossiers `media/` et la répartition
   est publiée par tome, **avec et sans** `Pride and Prejudice`.
2. `sources/<Projet>/bible.yaml` existe, se charge, se sauve sans perdre un champ rempli à la main,
   et `verifier_coherence` refuse un nom absent du glossaire. `glossaire.yaml` est **inchangé
   octet pour octet** sur les 5 projets, sauf usage explicite de `--ecrire-genre`.
3. Aucun attribut n'est présent dans une `bible.yaml` sans `citations[]`. Un test le prouve.
4. `tools/bible.py --revue` permet de traiter un projet de 24 personnages en moins de 20 minutes
   chronométrées. Si c'est plus, dites-le : c'est l'ergonomie qui décide si la bible sera remplie.
5. Le genre est résolu sur au moins **30 des 150** personnages qui n'en ont pas, ou le document
   explique pourquoi le corpus ne le permet pas.
6. Aucune image, aucun recadrage, aucun nom d'œuvre n'apparaît dans un fichier suivi par git.
   Vérifiez par `git status --porcelain` **et** `git check-ignore -v` sur les chemins produits.
7. `ruff check .` passe, `pytest -q -m "not modeles and not lent"` passe, et des tests neufs
   existent pour L23.1, L23.2 et L23.4 — dont au moins un qui aurait échoué avant le lot.
8. Le bloc `style:` existe pour chaque tome mesuré : **signature avec son `echantillon`**, 2 à 5
   ancrages **validés à la main**, et l'écart de signature entre tomes d'une même œuvre est publié.
9. Le document `docs/bible-visuelle-<date>.md` publie **ce que la mesure ne dit pas**.

## 4. Ce que ce lot ne fait pas, et ne doit pas commencer à faire

- Il ne génère aucune image et n'installe aucun modèle génératif.
- Il ne fait pas de détection de visage, ni de recadrage automatique « intelligent » : le recadrage
  est **proposé** par un rectangle sur la région décrite, et **validé** par un humain. Pas d'OpenCV
  (interdit n° 4), pas de nouvelle dépendance lourde.
- Il ne touche ni `manga/checkpoints.py:STAGES`, ni `FORMAT_VERSION`, ni `.checkpoints/`. La bible
  n'est pas une étape de pipeline : elle n'invalide rien.
- Il n'entre pas dans le prompt du traducteur. La bible est un référentiel visuel ; le seul champ
  qui peut traverser vers la traduction est `genre`, et par un geste explicite.
