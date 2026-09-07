# PLAN 24 — Le socle génératif : la frontière, le moteur, la trace

> **Lire `00-CONTEXTE-AGENT.md` puis `README-ILLUSTRATION-23-27.md` d'abord.**
>
> **Nature attendue** — **MINEUR**. Nouvelle brique opt-in, isolée, qui n'ouvre aucun fichier
> existant en écriture et ne change rien au chemin nominal. Rien dans ce lot ne justifie un MAJEUR :
> si vous en trouvez un motif, c'est le signe que vous avez touché quelque chose qui ne vous
> appartient pas.
>
> **Charge estimée** — 12 jours, dont 3 de mesure pure avant toute ligne de code de génération.
>
> **⚠ Prérequis : `PLAN-23`.** Sans bible, ce lot génère des images de personne. Il est
> techniquement exécutable sans elle — il ne doit pas l'être.
>
> **⚠ Ce plan ne renégocie PAS le principe « l'IA ne dessine jamais »** : la brique ne modifie
> aucune image existante, elle en crée de nouvelles (décision d'Alexandre du 2026-08-27, voir le
> README de série §4). Ce qu'il demande est une **phrase de portée** dans `docs/README.fr.md` et
> dans l'interdit n° 3, plus **un test** qui rende la frontière vérifiable. La renégociation du
> principe, elle, reste l'affaire exclusive du `PLAN-22`, et la phrase de portée écrite ici **ne
> doit pas lui servir de précédent**.

---

## 1. Trois questions, et aucune n'est technique en premier

Ce lot ne consiste pas à faire tourner un modèle. Il consiste à répondre à trois questions dans le
bon ordre, dont deux ont une réponse écrite quelque part dans le dépôt ou dans la loi.

| | Question | Où est la réponse aujourd'hui |
|---|---|---|
| 1 | Où passe exactement la frontière entre « lire l'œuvre » et « dessiner sur l'œuvre » ? | `docs/README.fr.md` l'énonce mais ne la borne pas, et l'interdit n° 3 la traite comme absolue |
| 2 | Qu'est-ce que la loi exige d'un logiciel qui produit des images de synthèse ? | AI Act art. 50(2), applicable depuis le **2026-08-02** — 25 jours avant l'écriture de ce plan |
| 3 | La machine d'Alexandre peut-elle enchaîner LLM puis modèle d'image sur 20 Go ? | Nulle part. Personne n'a mesuré |

## 2. Étape 0

### 0.1 — Écrire la frontière, et la rendre testable

**La brique ne modifie aucune image existante.** Elle lit `media/`, elle écrit des fichiers qui
n'existaient pas. Les quatre occurrences du principe dans le code restent donc vraies mot pour mot
(`manga/orchestrator_manga.py` ≈ l. 3041, `manga/relecture.py` l. 16, `manga/text_detection.py`
l. 29, `docs/README.fr.md` l. 1820), et l'invariant pixel-exact de `manga/clean.py` — une seule
écriture, `out_arr[paint] = style.background`, précédée de `paint = paint & region.mask`, vérifiée
hors masque par `tests/test_manga_clean.py` — n'est ni touché ni contourné.

**Ce qu'il faut écrire** — trois endroits, la même phrase, une fois :

1. `docs/README.fr.md`, sous le principe : sa **portée**. Proposition :

   > Le principe porte sur les **pixels de l'œuvre** : aucune écriture non déterministe dans une
   > planche, une page ou un fichier source. Une brique qui ne modifie **aucun** fichier existant
   > n'entre pas dans son périmètre : elle produit des fichiers neufs, dans un dossier qui lui est
   > propre, marqués comme générés, et supprimables sans rien casser. L'effacement de pixels
   > existants, lui, reste interdit hors du cadre que le `PLAN-22` définira.

2. `00-CONTEXTE-AGENT.md`, interdit n° 3 : la même borne, pour qu'une session future ne s'arrête pas
   à tort — ni ne se croie autorisée à trop.
3. `docs/ai-provenance.md` : la date, la décision, et le fait qu'elle vient d'Alexandre.

**Ce qu'il faut tester**, parce que le dépôt ne se contente jamais d'un raisonnement là où un test
existe — `clean.py` garde son masque redondant « parce que l'invariant ne doit pas dépendre d'un
raisonnement ». Trois tests, dans `tests/test_illustration_frontiere.py` :

- `illustration/` **n'importe** aucun module de `manga/`, `pipeline/`, `scan/` ni `gui/` ;
- aucune fonction de `illustration/` n'ouvre en mode écriture un chemin qui **existe déjà**
  (le test intercepte `open`/`Path.write_*`/`Image.save` sur un arbre témoin peuplé, et échoue si un
  fichier préexistant est visé) ;
- une génération complète via `MoteurFactice` sur un tome témoin laisse **tous** les fichiers
  préexistants inchangés, empreinte SHA-256 par fichier avant/après.

Ce troisième test est l'exact équivalent, pour la nouvelle brique, de ce que
`tests/test_manga_clean.py` fait pour `clean.py`. C'est lui qui transforme la frontière en propriété.

### 0.1 bis — Le déroulé en deux phases, et il est imposé

**Décision d'Alexandre du 2026-08-27** — la brique ne tourne jamais en même temps que la traduction,
et les deux modèles ne coexistent jamais en VRAM :

| Phase | Modèle chargé | Entrées | Sorties |
|---|---|---|---|
| 1 — préparation | LLM local `yume-27b` (base Qwen 3.8 27B) | `bible.yaml`, `glossaire.yaml`, texte traduit, images de `media/` | le **prompt proposé** + la **liste des images de référence retenues**, écrits dans un fichier de requête |
| **porte** | aucun | le fichier de requête | l'utilisateur relit, corrige, valide, ou annule |
| 2 — génération | modèle d'image | la requête **validée** + les images retenues | les PNG marqués + leur sidecar de provenance |

Trois exigences qui en découlent, et qui sont des critères de ce lot :

1. **La requête est un artefact persisté**, pas une variable en mémoire. C'est elle qui rend la porte
   humaine possible, la reprise possible, et le rejeu possible.
2. **La bascule de modèle a lieu une fois par run**, jamais une fois par image. Mesurez son coût
   (déchargement + chargement + rechargement final) et publiez-le à côté du temps de génération : si
   la bascule coûte plus que 8 images, c'est la bascule qu'il faut optimiser, pas le modèle.
3. **Aucun PNG n'existe sans qu'un humain ait validé le prompt qui l'a produit.** Le sidecar de
   provenance porte cette validation (qui, quand, prompt avant/après correction). C'est la ligne
   exacte que la politique IA du dossier NLnet exige de pouvoir montrer.

### 0.2 — L'obligation de marquage, à établir avant de produire le premier pixel

**AI Act, article 50(2)** — vérifié le 2026-08-27 sur
[artificialintelligenceact.eu](https://artificialintelligenceact.eu/transparency-rules-article-50/) :
le fournisseur d'un système d'IA qui génère des images de synthèse doit s'assurer que les sorties
sont **marquées dans un format lisible par machine** et **détectables comme générées par IA**.
Applicable depuis le **2026-08-02** ; les systèmes déjà sur le marché avant cette date ont jusqu'au
**2026-12-02**. Exemptions : fonction « purement assistive de l'édition standard » ou qui « n'altère
pas substantiellement les données d'entrée ». L'art. 50(4) (divulgation, obligations réduites pour
les œuvres artistiques) concerne le **déployeur** qui rend public — ce n'est pas le cas d'Alexandre,
qui garde ses images pour lui, mais **ça n'exonère pas le logiciel**.

⚠ **Ce plan n'est pas un avis juridique.** Écrivez la lecture retenue dans
`docs/ai-provenance.md`, avec la date et le lien, et notez qu'elle reste à confirmer. Deux raisons de
ne pas la traiter comme un détail : le dossier NLnet exige déjà une position publique sur l'IA
générative dans le README, et une brique génératrice non marquée contredirait cette position au
moment même où elle est écrite.

**Décidez et écrivez :** Angelith devient-il, en livrant cette brique, « fournisseur d'un système
générant des images de synthèse » ? La réponse honnête est probablement oui, y compris si un seul
utilisateur s'en sert. Alors le marquage n'est pas une option de configuration, c'est le
comportement par défaut, et il n'y a pas de clé pour l'éteindre.

### 0.3 — Le moteur, mesuré sur la vraie machine

Alexandre annonce « le modèle fait environ 10 Go en 4 bits ». **C'est le transformeur seul, et
la VRAM résidente n'est pas la taille du fichier.** Les chiffres publiés pour les GGUF de
`Qwen-Image-2512` (20 Md) donnent Q4_0/Q4_K_S à **11,9-12,3 Go** et Q4_K_M à **13,1 Go**, hors
encodeur de texte `Qwen2.5-VL-7B` et hors VAE.

Et le budget est déjà occupé : `docs/README.fr.md` (≈ l. 639) écrit que « ~17 Go ne tiennent de toute
façon pas dans 20 Go de VRAM. Ça supprime tout scénario de seconde instance / partage de VRAM ».
Le LLM de traduction **occupe la carte**. Conclusion structurelle, pas négociable :

> **La génération d'image et la traduction ne coexistent jamais en VRAM.** Le moteur d'image
> appelle `core/power.py:ollama_unload(base_url, model)` avant de charger ses poids, et le
> rechargement du LLM est de la responsabilité de l'appelant. Ce mécanisme existe déjà et est déjà
> utilisé : `docs/README.fr.md` (≈ l. 1927) décrit le déchargement automatique du LLM avant
> détection/OCR quand `DmlExecutionProvider` est actif. **Réutilisez-le, n'en écrivez pas un
> second.**

Mesurez **les trois chemins**, sur la 7900XT, sous Windows, avec le même prompt et la même graine :

| Chemin | À mesurer | Risque connu |
|---|---|---|
| **ComfyUI local** (API HTTP, comme Ollama) | temps par image 1328×1328, VRAM résidente au pic, stabilité sur 20 images d'affilée | support ROCm officiel sous Windows annoncé le 2026-01-06 (ROCm 7.1.1) ; des utilisateurs signalent des plantages et une sous-utilisation sur GGUF |
| **`stable-diffusion.cpp`** en sous-processus (Vulkan, GGUF) | idem | pas de ROCm requis ; le plus proche de la culture du projet (un binaire, un cache, pas de framework) ; support Qwen-Image à vérifier à la version |
| **`diffusers` en pur Python** | idem | ROCm/Windows sous `diffusers` est le terrain le plus fragile ; ajoute une dépendance très lourde au dépôt |

**Publiez le tableau des trois, et le motif d'abandon de ceux que vous écartez.** Trois chiffres
suffisent à décider : secondes par image, pic de VRAM, taux d'échec sur 20 images.

⚠ **Le critère de choix n'est pas la vitesse.** C'est : *combien de dépendance le dépôt avale-t-il ?*
Un serveur HTTP local que l'utilisateur installe lui-même, comme Ollama, ne pèse **rien** dans
`requirements-*.txt`. Un `import diffusers` pèse des gigaoctets et met le dépôt en dette de
compatibilité ROCm. Le dépôt a déjà refusé OpenCV pour ~60 Mo (interdit n° 4) : la cohérence commande
un client, pas un framework.

### 0.4 — Le modèle, licence vérifiée à la source primaire

| Candidat | Ce qu'il apporte | À vérifier avant usage |
|---|---|---|
| `Qwen-Image-2512` (20 Md, **Apache-2.0**, 2025-12-31) | texte-vers-image pur, réalisme et rendu de texte améliorés | rien de bloquant ; **ne conditionne pas sur une image de référence** — donc ne résout pas « le bon personnage » à lui seul |
| `Qwen-Image-Edit-2511` (20 Md, **Apache-2.0**, 2025-12-23) | **plusieurs images de référence**, « character consistency significantly improved » | c'est le candidat naturel du `PLAN-25` |
| `Qwen-Image-2.0` (7 Md, 2026-02-10) | 2K natif, génération + édition unifiées, « multi-panel comic with consistent characters » ; **7 Md tiennent dans 20 Go sans quantisation agressive** | **licence non établie** : la page Hugging Face répondait 401 le 2026-08-27. Sans licence claire, **on ne l'utilise pas** |

**La règle du dépôt s'applique telle quelle** : `docs/mesures/detecteurs-candidats-2026-08-26.md` et le
`PLAN-22` ont établi la jurisprudence — la licence des **poids** se vérifie à la source primaire, et
« licence du code Apache-2.0 » ne dit rien de la licence des poids. Le projet est **AGPL-3.0** et
utilise déjà des poids GPL-3.0 (détecteur de bulles, `comic-text-detector` + Manga109-s
académique) : ajouter un poids dont la licence est inconnue serait le premier de la série à ne pas
avoir de justification écrite.

Écrivez le verdict dans `manga_models/README.md` (ou un `models/README.md` neuf si la brique a son
propre dossier de poids) avec la date, l'URL et l'empreinte SHA-256 du fichier récupéré.

---

## L24.1 — La quatrième brique, et elle est isolée

Point d'entrée **`run_illustration.py`**, module **`illustration/`**, sur le modèle exact de
`scan/` : orchestrateur propre, aucune importation depuis `manga/` ni `pipeline/`, et
`core/` seulement. Le graphe d'imports internes du dépôt est **sans cycle** et c'est un argument de
dossier de financement : `core` n'importe rien d'interne, `pipeline`→core, `manga`→core,
`scan`→core+manga, `gui`→manga+core. **`illustration`→core, et rien d'autre.** Si vous avez besoin
d'une fonction de `manga/`, remontez-la dans `core/`.

`core/version.py:ETAT_BRIQUES` reçoit une quatrième entrée. Le mot d'état doit être **nouveau et
plus bas que `beta`** — proposition : `"experimental"` — et le commentaire au-dessus doit nommer la
réserve, comme il le fait déjà pour `scan` et pour la lecture hors bulle. Cherchez et mettez à jour
tout test qui énumère `ETAT_BRIQUES` et l'affichage de `--version`.

⚠ **La brique n'entre pas dans le graphe d'invalidation.** Elle n'ajoute rien à
`manga/checkpoints.py:STAGES`, n'incrémente pas `FORMAT_VERSION`, ne lit ni n'écrit sous
`.checkpoints/`. Son cache est à elle : `build/<Projet>/<Tome>/illustrations/`. Interdit n° 1 —
« une relance de tome coûte des heures de GPU », et `load_regions` rend `None` sur écart de version,
ce qui déclencherait `downstream("detection")` **sur tous les projets**.

## L24.2 — Le client, pas le framework

`illustration/moteur.py` — une interface, deux implémentations au plus :

```python
class Moteur(Protocol):
    def disponible(self) -> bool: ...
    def generer(self, requete: Requete) -> Sortie: ...   # Sortie porte PNG + métadonnées
```

`Requete` est un **dataclass gelé**, et sa forme est celle des **canaux du moteur**, pas celle d'une
phrase : prompt (texte), prompt négatif (texte), **références** (chemins d'images — le canal qui
porte l'identité), **canaux structurés** optionnels (entités + masques façon `EliGen`, image de
contrôle façon ControlNet — voir `PLAN-26` étape 0.4), puis dimensions, graine, pas, guidage, modèle.
`Sortie` porte les octets PNG **et** le dictionnaire de provenance de L24.3.

⚠ **Un `Moteur` qui n'expose que `prompt` est un cul-de-sac.** Prévoyez les canaux dès l'interface,
même si le premier moteur n'en implémente aucun : `generer` doit pouvoir **refuser explicitement** un
canal qu'il ne sait pas honorer (motif nommé), jamais l'ignorer en silence — une requête dont le
masque a été jeté sans un mot produirait une image plausible et fausse, et personne ne saurait
pourquoi.

⚠ **Le texte reste du texte.** Ne sérialisez jamais la `Requete` entière dans le champ prompt : le
JSON y coûte des tokens sans porter de structure lisible par l'encodeur. Le format de ce champ est
une question mesurée au `PLAN-26` étape 0.3, pas une préférence. Les deux sont sérialisables et testables **sans moteur** — un `MoteurFactice` déterministe
(qui rend un PNG uni dont la couleur dérive de la graine) permet de tester toute la brique en CI,
sans poids et sans GPU, donc **hors marqueur `modeles`**.

Configuration : un bloc `illustration:` dans `config.yaml`, dans le style du fichier — de la prose
commentée qui justifie chaque valeur par un chiffre (interdit n° 5 : `config.yaml` est un document
de 95 Ko, aucun aller-retour `yaml.safe_dump` ne doit l'écraser). Chaque clé doit être déclarée dans
`core/config_schema.py:CLES_CONNUES` **et** dans la table de types, sinon
`tests/test_config_valide.py` échoue en nommant la clé — c'est voulu, c'est le filet.

Défaut : `illustration.actif: false`. Un utilisateur qui ne touche à rien ne voit **aucune**
différence, ne télécharge **aucun** poids, et ne perd **aucune** seconde au démarrage.

**Et la `Requete` s'écrit sur le disque, parce que le run a deux phases** (étape 0.1 bis) :

```powershell
python run_illustration.py --check                        # environnement et poids
python run_illustration.py "<Projet>" <Tome> --phase prompt   # phase 1 : LLM → requete.yaml
#   … l'utilisateur relit et corrige build/<Projet>/<Tome>/illustrations/requete.yaml …
python run_illustration.py "<Projet>" <Tome> --phase image    # phase 2 : bascule + génération
python run_illustration.py --rejouer <image>.provenance.json  # rejeu d'une requête passée
```

`requete.yaml` est le **format d'échange entre les deux phases et l'humain** : lisible, éditable à la
main, commenté, avec un champ `valide: false` que l'utilisateur passe à `true` — ou que l'interface
passe pour lui (`PLAN-27`). ⚠ **La phase 2 refuse de démarrer sur `valide: false`**, et le motif de
refus est nommé. C'est le seul garde-fou qui garantisse la porte humaine ; un défaut à `true`
l'annulerait.

⚠ **Ce n'est pas un `.checkpoints/` et il ne faut pas le confondre avec un.** `requete.yaml` vit
sous `build/<Projet>/<Tome>/illustrations/`, il n'entre pas dans `manga/checkpoints.py:STAGES`, et son
absence ou son incohérence ne déclenche **aucune** invalidation en amont (interdit n° 1). `--phase`
n'est pas `--from` : ce sont deux mécaniques distinctes, ne réutilisez pas le nom.

## L24.3 — Le marquage, et il n'a pas d'interrupteur

Chaque PNG produit porte, **dans le fichier** :

- un bloc `tEXt`/`iTXt` PNG : `Software=Angelith <version>`, `Generator=<modèle + révision>`,
  `AIGenerated=true`, `Seed`, `Prompt` (tronqué), `SourceWork=<identifiant local, jamais le titre
  commercial>` ;
- un **manifeste de provenance** à côté : `<image>.provenance.json` — modèle, empreinte SHA-256 des
  poids, graine, prompt complet, prompt négatif, chemins des références, empreinte de `config.yaml`,
  version d'Angelith, date, et la phrase « image générée par IA, ne fait pas partie de l'œuvre
  source » ;
- **C2PA si et seulement si** une bibliothèque acceptable existe sans traîner un SDK entier : à
  mesurer, et à documenter comme non fait si ça ne tient pas. Un `tEXt` + sidecar est un marquage
  lisible par machine ; c'est un plancher défendable, pas un idéal.

**Un test doit prouver que le marquage est inamovible** : générer via `MoteurFactice`, relire le
PNG, vérifier la présence des champs. Et un second test doit prouver qu'**aucun chemin de code ne
sait produire un PNG sans marquage** — c'est-à-dire que l'écriture passe par une seule fonction.

⚠ **Le nom de l'œuvre ne va pas dans les métadonnées.** Un identifiant local suffit. Le
`.gitignore` du dépôt refuse déjà d'exposer les titres ; une image qui les porte dans son XMP les
exposerait le jour où elle est partagée par erreur.

## L24.4 — Le téléchargement de 12 Go n'est pas celui de 104 Mo

`manga/models.py` a le bon patron : `telecharger(url, destination, octets_attendus=…)`,
`empreinte()` en SHA-256 par blocs de 1 Mio, `assurer_modele(chemin, url=…, auto=True)`, et des
constantes explicites (`DETECTEUR_OCTETS = 108_982_949`). Reprenez-le **en changeant trois choses** :

1. `auto=False` par défaut. Un téléchargement de 12 Go ne se déclenche pas parce qu'un utilisateur a
   lancé une commande : il se demande. `run_illustration.py --check` le fait au bon moment — c'est
   déjà la doctrine du dépôt pour les 104 Mo du détecteur (« quand tu prépares la machine plutôt
   qu'au milieu d'un tome »).
2. **Reprise sur coupure** obligatoire (requête `Range`), et vérification de l'empreinte avant
   usage. Un fichier de 12 Go tronqué qui produit du bruit coûterait une soirée de diagnostic.
3. Le poids ne va **pas** dans `manga_models/` — dossier de la brique manga, et `*.onnx` est
   gitignoré mais pas `*.gguf`/`*.safetensors`. Ajoutez les motifs au `.gitignore` **dans le même
   commit** que le module de téléchargement, jamais après.

## L24.5 — La première image, reproductible

Le critère de fin de ce lot n'est pas « une belle image ». C'est :

> **Deux exécutions de la même `Requete`, même graine, même modèle, même `config.yaml`, produisent
> deux PNG identiques octet pour octet — ou l'écart est mesuré et expliqué.**

Écrivez la mesure : sur 5 requêtes × 3 exécutions, combien sont bit-à-bit identiques. Si le backend
n'est pas déterministe (c'est fréquent), **dites-le** et remplacez le critère par une distance
mesurée, avec sa valeur. Un lot qui publie « le backend n'est pas reproductible, voici de combien »
est un lot réussi ; un lot qui affirme la reproductibilité sans l'avoir mesurée ne l'est pas.

## L24.6 — Le rapport, et le journal

`RAPPORT.md` du tome reçoit une section « Illustrations générées » : combien, avec quel modèle, quelle
graine, et le rappel qu'elles ne font pas partie de l'œuvre. `perf.log` reçoit le temps par image et
le pic de VRAM si le backend le rapporte.

Et `docs/ai-provenance.md` reçoit **la décision de l'étape 0.1, la lecture de l'art. 50 de
l'étape 0.2, et le prompt de chaque session Claude Code de cette série**. C'est une exigence du
dossier NLnet, pas une coquetterie : les livrables purement générés par IA ne sont pas éligibles au
paiement, et la traçabilité est ce qui distingue « assisté » de « généré ».

---

## 3. Les critères de ce lot

1. La **phrase de portée** de l'étape 0.1 est écrite aux trois endroits (`docs/README.fr.md`,
   interdit n° 3 du `00-CONTEXTE-AGENT.md`, `docs/ai-provenance.md`), datée, attribuée à Alexandre,
   et elle dit explicitement qu'elle **ne préjuge pas** de ce que le `PLAN-22` décidera.
1 bis. Les **trois tests de frontière** existent et passent : pas d'import de `manga/`,
   `pipeline/`, `scan/`, `gui/` ; aucune ouverture en écriture d'un chemin préexistant ; un run
   complet sur un tome témoin laisse toutes les empreintes SHA-256 préexistantes inchangées.
1 ter. Le run se fait en **deux phases** avec un `requete.yaml` persisté, la phase 2 **refuse**
   `valide: false`, et le coût de la bascule de modèle est mesuré et publié à côté du temps de
   génération.
2. La lecture de l'art. 50(2) est écrite, datée, sourcée, et signalée comme à confirmer.
3. Les trois chemins d'exécution sont mesurés sur la 7900XT (secondes/image, pic VRAM, échecs/20) et
   le motif d'abandon des écartés est publié.
4. La prémisse « ~10 Go en 4 bits » est **confirmée ou corrigée avec son dénominateur** :
   transformeur seul contre VRAM résidente totale, encodeur de texte compris.
5. `illustration/` n'importe que `core/`, **et un test neuf le vérifie**. ⚠ Aucun test du graphe
   d'imports n'existe aujourd'hui dans `tests/` — la propriété « sans cycle » a été constatée à la
   main lors d'un audit, jamais protégée. Écrivez-le : il vaut pour les quatre briques, pas
   seulement la nouvelle, et c'est un garde-fou gratuit pour un argument de dossier de financement.
6. `illustration.actif: false` par défaut ; un run `python run.py` et un run `python run_manga.py`
   sont **iso-comportement**, empreinte SHA-256 de `config.yaml` mise à jour et annoncée.
7. Aucun PNG ne peut sortir de la brique sans marquage ni sidecar de provenance. Deux tests. Le
   sidecar archive le **payload JSON exact** envoyé au moteur, canaux compris.
7 bis. `Moteur.generer` **refuse avec un motif nommé** tout canal qu'il ne sait pas honorer. Un test
   le prouve : aucun canal n'est ignoré en silence.
8. Aucun poids, aucune image, aucun titre d'œuvre n'entre dans git. `git check-ignore -v` le prouve.
9. `ETAT_BRIQUES` porte la quatrième brique avec un état plus bas que `beta` et sa réserve nommée.
10. `ruff check .` passe ; `pytest -q -m "not modeles and not lent"` passe **sans aucun poids
    installé**, grâce à `MoteurFactice`.
11. `docs/socle-generatif-<date>.md` reprend ces critères un par un, y compris les non tenus, et dit
    ce que la mesure ne dit pas.

## 4. Ce que ce lot ne fait pas

- Il ne prétend **rien** sur la ressemblance du personnage. C'est le `PLAN-25`, et l'annoncer ici
  serait le genre d'affirmation que `docs/mesures/webtoon-2026-08-26.md` a dû venir démentir.
- Il n'insère aucune image dans un DOCX, EPUB ou PDF. C'est le `PLAN-27`.
- Il n'affine aucun modèle.
- Il ne touche pas `manga/clean.py`, ni `manga/typeset.py`, ni leurs tests.
- Il ne modifie **aucune** image existante, et il n'ajoute aucun chemin de code capable de le faire.
  Si un besoin de retouche apparaît, il ouvre une question qui appartient au `PLAN-22`, pas ici.
- Il ne génère rien sans qu'un humain ait validé le prompt. Il n'ajoute **aucun** mode « tout
  automatique », même derrière un drapeau.
