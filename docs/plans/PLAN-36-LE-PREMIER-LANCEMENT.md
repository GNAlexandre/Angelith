# PLAN 36 — Le premier lancement : le diagnostic structuré, les dépendances, les poids

> **Lire `00-CONTEXTE-AGENT.md`, puis `README-INTERFACE-31-37.md`.**
>
> **Nature attendue** — **MINEUR**. Aucune clé obligatoire, aucun cache invalidé. L36.1
> refactorise deux doctors : leur sortie console doit rester **iso**, sinon c'est un MAJEUR de
> fait pour qui scripte `run_manga.py --check`.
>
> **Charge estimée** — 9 jours, dont 2 pour l'inventaire de l'étape 0 seul.
>
> **Prérequis : `PLAN-31`** (l'accueil doit exister pour porter l'état). **Prérequis du
> `PLAN-37`** : un `.exe` livré sans ce lot est un `.exe` qui échoue chez l'utilisateur sans
> dire pourquoi.

---

## 1. L'état, relevé à la source le 2026-09-04 (2.24.1, `8e5ee5a`)

### 1.1 Ce dont une installation complète a besoin

Cinq fichiers `requirements-*.txt`, et **rien** qui les réunisse (pas de `pyproject.toml` — la
docstring de `core/version.py` le dit et l'assume : « le projet n'est pas empaqueté, il se lance
par `python run.py` »).

| Dépendance | Origine | Requise par | Non-pip ? |
|---|---|---|---|
| `openai`, `httpx`, `pyyaml`, `pymupdf`, `python-docx`, `rich`, `pytest` | pip | socle | — |
| `PySide6>=6.7` | pip | interface | — |
| `numpy`, `onnxruntime` | pip | manga (détection) | — |
| `manga-ocr>=0.1.14` | pip | manga, scan (OCR japonais) | ⚠ **tire `torch` + `transformers`** |
| `rapidocr-onnxruntime` | pip | manga (OCR latin) | — |
| `rarfile>=4.1` | pip | `.cbr` | ⚠ exige l'outil externe `unrar` / `unar` |
| **Ollama** (ou tout endpoint OpenAI-compatible) | installateur | toute traduction | ⚠ oui |
| **Pandoc** | installateur | sorties DOCX du LN | ⚠ oui |
| **WeasyPrint** (ou LaTeX) | pip + libs système | sorties PDF du LN | ⚠ oui, en partie |
| **poids de détection** sous `manga_models/` | téléchargement | manga | ⚠ oui, et voir 1.3 |
| **modèle `manga-ocr`** | Hugging Face, au premier usage | manga, scan | ⚠ oui, silencieux |
| **ComfyUI** + poids Qwen-Image | installateur + téléchargement | illustration | ⚠ oui |
| **polices** | `tools/installer_polices.ps1`, `tools/polices.py` | rendu des planches | ⚠ oui |

⚠ **`torch` n'est pas installé dans tous les environnements de travail** — vérifié : un import
`torch` échoue dans l'environnement de cette session. Ce n'est pas un défaut, c'est la preuve
que la brique manga est **optionnelle en pratique** et que l'application doit savoir se décrire
avec des briques absentes.

### 1.2 Ce que le diagnostic sait déjà faire, et comment il est affiché

Deux doctors, un par brique, et ils sont dans la bonne couche : `pipeline/doctor.py:run_doctor`
et le doctor manga (`run_manga.py --check`) — « le diagnostic appartient à la BRIQUE qu'il
examine (sections de config, chemins, Pandoc, moteur PDF), pas à une CLI » (`app.py`). Les
sections réellement communes (Ollama, dépendances, conclusion) vivent dans `core/`.

`pipeline/doctor.py` vérifie déjà finement : `reference.docx` et `epub.css` **seulement si leur
format est demandé** (L96-114). C'est le bon niveau de finesse.

⚠ **Mais l'affichage graphique est une capture de texte.** `fenetre.py:_capturer_diagnostic`
(L1476) et `_capturer_test_llm` (L1495) redirigent la sortie **console** dans un
`DialogueTexte` (`gui/dialogues.py` L252). Conséquences :

- aucun geste n'est attaché à un problème — le texte dit ce qui manque, pas quoi faire ;
- rien n'est réutilisable : ni pour l'accueil du `PLAN-31` L31.6, ni pour le dépôt guidé du
  `PLAN-34` L34.3 (qui a besoin de savoir si `unrar` existe **avant** de proposer l'import), ni
  pour un `.exe` qui doit se diagnostiquer chez l'utilisateur ;
- le dialogue **bloque** le temps du diagnostic, qui comprend un appel réseau.

### 1.3 Les licences, et c'est le point dur de ce lot

| Poids | Licence | Redistribuable ? |
|---|---|---|
| détecteur en place (`comic-text-detector`) | **GPL-3.0 + Manga109-s** | ⚠ **non** — Manga109-s a ses propres conditions d'usage |
| `ogkalu/comic-speech-bubble-detector-yolov8m` | Apache-2.0 (vérifiée 2026-08-26) | oui, mais **ce n'est pas un détecteur de bulles** — 0 ballon sur 33 régions labellisées |
| `manga-ocr` | modèle Hugging Face, téléchargé au premier usage | à vérifier à la source primaire |
| Qwen-Image | Apache-2.0 (vérifiée 2026-08-26), 20 Md | oui |
| `Qwen-Image-EliGen-V2`, contrôlenet `MODEL_PATCH` | Apache-2.0 (vérifiée 2026-08-30) | oui, non installés |
| LaMa | ⚠ **licence non établie** | non — à vérifier avant tout usage |

⚠ **Conclusion à écrire noir sur blanc dans ce lot : Angelith ne redistribue aucun poids.** Il
les **récupère**, avec consentement, en affichant la licence, et en enregistrant l'empreinte
SHA-256 de ce qu'il a récupéré. C'est la seule position tenable, et elle est cohérente avec la
règle §5 bis du contexte agent (une licence vérifiée porte sa date) et avec le marquage AI Act
art. 50 déjà livré par la brique illustration.

---

## 2. Étape 0 — l'inventaire des pannes, par masquage

### 0.1 — Ce qui se passe aujourd'hui quand chaque dépendance manque

C'est la mesure de ce lot, et elle est faisable sans machine neuve : **masquez chaque dépendance
une par une** (renommer un exécutable dans le `PATH` d'un sous-processus, désinstaller dans un
venv jetable, arrêter Ollama, déplacer `manga_models/`) et relevez ce que l'utilisateur voit.

| Dépendance masquée | Message obtenu aujourd'hui | Dit-il quoi faire ? | Où apparaît-il |
|---|---|---|---|
| Ollama arrêté | | | |
| PySide6 absent | `gui.py` L…: message explicite avec la commande pip | ✅ déjà bon | `SystemExit` |
| Pandoc absent | | | |
| `unrar` absent | | | |
| poids ONNX absents | | | |
| modèle `manga-ocr` non téléchargé, hors réseau | | | |
| police manquante | | | |
| ComfyUI arrêté | | | |

⚠ **`gui.py` porte déjà le bon exemple** : PySide6 absent produit « L'interface graphique demande
PySide6, qui n'est pas installé. → pip install -r requirements-gui.txt (les CLI `run.py` et
`run_manga.py` fonctionnent sans.) » — un message qui nomme la cause, le geste, **et ce qui
marche quand même**. C'est le gabarit de tous les autres.

⚠ **Et le cas silencieux est le pire** : `manga-ocr` télécharge son modèle depuis Hugging Face
au premier usage. Que fait-il sans réseau, au milieu de la planche 12 d'un run de nuit de trois
heures ? **Mesurez-le**, parce que c'est le mode de panne d'un utilisateur qui a lancé un run
avant de se coucher.

### 0.2 — Ce qu'un geste réparateur a le droit d'être

Trois classes, à écrire avant d'implémenter quoi que ce soit :

| Classe | Exemples | Geste autorisé |
|---|---|---|
| **récupérable avec consentement** | poids ONNX, modèle Ollama, modèle `manga-ocr`, polices libres | téléchargement, licence affichée **avant**, SHA-256 enregistrée après |
| **installable par l'utilisateur seul** | Pandoc, `unrar`, ComfyUI, WeasyPrint | ⚠ **jamais automatique** — un lien, une commande copiable, une revérification |
| **hors périmètre** | pilotes GPU, CUDA, droits d'administrateur | dire ce qui manque, et s'arrêter là |

⚠ **La ligne à ne pas franchir : Angelith n'installe aucun logiciel système.** Ni Pandoc, ni un
gestionnaire de paquets, ni un service. Le `PLAN-30` a déjà tranché le principe voisin pour
ComfyUI : « Angelith ne pilote pas le cycle de vie d'un programme que l'utilisateur a installé ;
le faire créerait une dépendance qu'aucune mesure ne justifie. »

---

## L36.1 — Le diagnostic rend une structure, puis s'affiche

`core/diagnostic.py` : les deux doctors **rendent** une liste de verdicts, et ce sont les
appelants qui impriment ou dessinent.

```python
@dataclass(frozen=True)
class Verdict:
    identifiant: str        # "pandoc"
    brique: str             # "ln" | "manga" | "scan" | "illustration" | "socle"
    gravite: str            # "bloquant" | "degrade" | "information"
    constat: str            # « Pandoc introuvable dans le PATH »
    consequence: str        # « les sorties DOCX du light novel ne seront pas produites »
    geste: str              # « installer Pandoc — https://pandoc.org/installing.html »
    reparable: bool         # un bouton peut-il le régler ? (cf. L36.2)
```

Trois exigences, et la première est la plus contraignante :

1. ⚠ **la sortie console reste iso, octet pour octet.** `run_manga.py --check` et
   `run.py --check` sont scriptés ; un test capture leur sortie avant et après le refactor et
   les compare. Le refactor consiste à **extraire** le constat de l'impression, pas à réécrire
   le texte ;
2. **`gravite` distingue « bloquant » de « dégradé »**, ce que la sortie texte actuelle mélange :
   Pandoc absent ne bloque pas un run manga, et affirmer le contraire dans l'accueil
   découragerait un utilisateur qui n'a besoin que du manga ;
3. **la structure est ce que consomment** l'accueil (`PLAN-31` L31.6), le dépôt guidé (`PLAN-34`
   L34.3) et le `.exe` (`PLAN-37` L37.7, qui la fait tourner en CI sur l'exécutable gelé).

## L36.2 — Le geste réparateur, quand il est sûr

Une page « Diagnostic » (en pied de la nav latérale, comme le veut la convention Fluent), qui
affiche les verdicts groupés par brique et par gravité, chacun avec son geste.

Ce qui est réparable **d'un bouton**, et à ces conditions :

| Réparation | Conditions non négociables |
|---|---|
| télécharger les poids de détection | licence affichée **avant** le clic ; SHA-256 enregistrée ; ⚠ pour un poids non redistribuable (GPL-3.0 + Manga109-s), le téléchargement se fait **depuis sa source primaire**, jamais depuis un miroir du projet |
| `ollama pull <modèle>` | endpoint local seulement ; taille annoncée ; annulable |
| télécharger le modèle `manga-ocr` | **avant** le run, pas au milieu — c'est tout l'objet |
| installer les polices | `tools/installer_polices.ps1` et `tools/polices.py` existent ; le bouton les appelle, il ne les réécrit pas |

Et les règles d'écriture :

1. ⚠ **rien ne se télécharge sans un clic explicite.** Pas de « préparation automatique au
   premier lancement » : un premier lancement qui consomme plusieurs gigaoctets sans demander
   est un défaut, quelle que soit l'intention ;
2. **la provenance est enregistrée** — URL, date, taille, SHA-256, licence — dans un fichier du
   dossier de poids. C'est la règle des chiffres appliquée aux artefacts, et c'est ce que le
   `PLAN-30` critère 2 exige déjà pour tout poids installé ;
3. **un téléchargement se reprend ou se refait proprement.** Un fichier partiel doit être
   détecté (par sa taille et son empreinte), pas chargé et laissé planter dans `onnxruntime` ;
4. ⚠ **aucun téléchargement pendant un run.** Le diagnostic est un préalable, jamais une
   réparation à chaud — un run de nuit qui se met à télécharger 2 Go n'est plus le run qu'on a
   lancé.

## L36.3 — L'accueil dit l'état, sans jamais bloquer

C'est L31.6 du `PLAN-31`, dont ce lot fournit la matière. Trois pastilles au plus sur l'accueil,
alimentées par `core/diagnostic.py`, calculées **hors du fil d'affichage**, avec un état
`inconnu` affichable :

- **traduction** : endpoint LLM joignable, et le modèle de la config présent dans sa liste ;
- **manga** : poids de détection présents, OCR disponible ;
- **sorties** : Pandoc / moteur PDF, selon les formats demandés par `config.yaml`.

⚠ **Pas de diagnostic complet au démarrage.** Le diagnostic complet est une page qu'on ouvre ;
l'accueil ne porte que les trois sondes dont le résultat change ce qu'on peut faire tout de
suite. Le `PLAN-31` a mesuré ce que coûte un démarrage qui en fait trop.

## L36.4 — Le premier lancement sans corpus, et il doit pouvoir faire quelque chose

Une installation neuve n'a aucune œuvre — et l'utilisateur ne peut pas en fournir une pour
essayer sans se poser la question des droits.

Le dépôt a déjà ce qu'il faut : `tools/corpus_synthetique.py` produit un corpus
**redistribuable sans réserve** (le contexte agent le dit), et `tools/captures_gui.py` fabrique
un tome synthétique complet — « deux ellipses noires sur gris, deux répliques » — qui « fait
fonctionner le chemin d'aperçu pour de vrai », le même montage que la fixture de
`tests/test_gui_editeur_direct.py`.

Ce lot en fait une capacité de l'application : **« Créer un tome de démonstration »**, un geste
de l'accueil, qui écrit un tome synthétique sous `sources/` et permet :

1. de lancer un run court de bout en bout (avec `--dry-run` si aucun LLM n'est joignable) ;
2. de voir la retouche fonctionner sur de vraies zones ;
3. de produire un CBZ et un PDF réels.

⚠ **Il est marqué comme démonstration** dans son nom de dossier, et il est supprimable sans
rien casser. Un utilisateur ne doit jamais confondre le tome de démonstration avec une œuvre.

⚠ **Et il ne dépend d'aucune police propriétaire** : `tests/conftest.py` fabrique sa planche
avec `C:/Windows/Fonts/msgothic.ttc` et **skippe** si la police manque. Pour un tome de
démonstration livré à un utilisateur, la police doit être celle que l'installation fournit — ou
le geste doit se refuser proprement en le disant, comme le `PLAN-20` L20.2 l'a demandé pour les
tests.

## L36.5 — Les licences se lisent depuis l'application

`LICENSE` (34 253 o, AGPL-3.0-or-later) et `NOTICE` (4 066 o) sont à la racine. `texte_a_propos`
(`gui/dialogues.py` L371) existe déjà.

⚠ **Le `NOTICE` nomme le projet « Angelith »**, et le contexte agent du 2026-08-26 s'interrogeait
sur ce point (« vérifier s'il s'agit d'un renommage ou d'une brique »). Au 2026-09-04, tout le
code applicatif dit « Angelith » : `gui.py` (`app.setApplicationName("Angelith")`), le titre de
fenêtre, `orchestrator_manga.py` L265, `.angelith/` pour les réglages. **La question est
tranchée dans les faits ; ce lot l'écrit** — Angelith est le nom public, Yume-Trad le nom du
dépôt de travail. C'est aussi ce que le `PLAN-37` devra graver dans l'installeur.

Ce que la page « À propos » doit porter après ce lot :

- la version (`core/version.py`, source unique) et l'état de chaque brique (`ETAT_BRIQUES`) ;
- la licence du logiciel, **et la liste des licences des poids présents sur la machine**, lue
  dans les fichiers de provenance écrits par L36.2 ;
- le rappel que les images générées sont marquées (AI Act art. 50(2)), qui est déjà un défaut
  sans interrupteur dans la brique illustration.

---

## 3. Les critères de ce lot

1. Le tableau de masquage de l'étape 0.1 est publié, une ligne par dépendance, avec le message
   obtenu **avant** le lot, et le message obtenu après. Le cas « `manga-ocr` sans réseau au
   milieu d'un run » est mesuré et nommé.
2. `core/diagnostic.py` rend des `Verdict` structurés ; les deux doctors le consomment ; la
   sortie console de `run.py --check` et `run_manga.py --check` est **identique octet pour
   octet** avant/après, vérifié par un test.
3. `gravite` distingue bloquant et dégradé, et un test vérifie qu'aucune absence propre au LN
   n'est classée bloquante pour un usage manga (et réciproquement).
4. La page Diagnostic affiche constat, conséquence et geste pour chaque verdict. Aucun verdict
   n'est affiché sans geste — ou son absence de geste est explicite (« hors périmètre »).
5. Aucun téléchargement ne part sans clic explicite ; aucun ne part pendant un run ; chacun
   affiche la licence **avant** et enregistre URL, date, taille et SHA-256 après.
6. Aucun logiciel système n'est installé par l'application. Un test vérifie qu'aucun chemin de
   réparation n'appelle un installateur ni un gestionnaire de paquets.
7. Un fichier de poids partiel est détecté avant usage, et le geste de reprise est proposé.
8. L'accueil affiche trois pastilles avec un état `inconnu` possible, sans sonde sur le fil
   d'affichage, et s'affiche en moins d'une seconde avec Ollama arrêté (critère 7 du `PLAN-31`,
   revérifié ici).
9. « Créer un tome de démonstration » produit un tome utilisable de bout en bout, marqué comme
   démonstration, supprimable, et se refuse **proprement** si la police nécessaire manque.
10. La page « À propos » liste la licence du logiciel et celles des poids réellement présents,
    lues dans les fichiers de provenance.
11. `ruff check .` passe ; `pytest -q -m "not modeles and not lent"` passe **sans réseau** — un
    test qui exigerait un téléchargement doit porter un marqueur.
12. `docs/mesures/premier-lancement-<date>.md` reprend ces critères un par un, y compris les non
    tenus, et dit ce que la mesure ne dit pas.

## 4. Ce que ce lot ne fait pas

- Il n'empaquette rien, ne produit aucun `.exe`, ne crée pas `pyproject.toml`. C'est `PLAN-37`.
- Il n'installe aucun logiciel système : ni Pandoc, ni `unrar`, ni ComfyUI, ni Ollama.
- Il ne redistribue **aucun** poids, et n'héberge aucun miroir.
- Il ne télécharge rien automatiquement, ni au premier lancement, ni pendant un run.
- Il ne modifie aucun seuil, aucun prompt, aucun chemin de traitement.
- Il ne prétend pas rendre la brique scan (bêta) ou la brique illustration installables en un
  clic : leur diagnostic dit ce qui manque, l'installation reste manuelle.
- Il ne remplace pas le `DialogueTexte` là où il sert encore (« Tester la connexion LLM » peut
  rester une capture de texte si sa sortie n'a pas de geste attaché).
