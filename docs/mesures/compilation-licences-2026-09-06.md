# Compiler en une commande, et dire la vérité sur les licences — mesure du 2026-09-06 (lot 38)

> **Machine** — PC principal, Windows 11 Pro 26200, Python 3.12.3, PyInstaller 6.22.2,
> Inno Setup 6.7.3. **Commit de départ** : `c8ea3c5` (2.31.0).
> **Empreinte SHA-256 de `config.yaml`** : `f879ce66ff58…` — **inchangée**. Ce lot ne touche pas
> à `config.yaml`, n'invalide aucun cache, et `manga/checkpoints.py:FORMAT_VERSION` reste à **3**.
>
> Ce document reprend les critères du lot un par un, y compris ceux qui ne sont pas tenus, et
> dit à chaque fois ce que la mesure ne dit pas.

---

## 1. Le défaut principal — le dépôt disait trois choses sur la même licence

### 1.1 Le relevé, avant correction

`grep -rn "Manga109"` sur le dépôt, le 2026-09-06, hors `tests/` : **46 occurrences dans 34
fichiers**. Ce n'est pas le nombre qui compte, c'est ce qu'elles disent du **détecteur de
bulles** :

| Source | Ce qu'elle dit du détecteur de BULLES | Verdict |
|---|---|---|
| `manga_models/README.md:25,113` | GPL-3.0, « telle que déclarée sur la page du modèle (relevé le 2026-08-25) » | exact, daté |
| `manga/reparations.py:176` | AGPL-3.0 (export YOLOv8-seg ; Ultralytics YOLOv8 est lui-même AGPL-3.0) | exact, non daté |
| `gui/sondes.py:175-176` | « le détecteur est **GPL-3.0 + Manga109-s** » | ⚠ **FAUX** |
| `manga/doctor.py:85` | « Le détecteur en place est **GPL-3.0 + Manga109-s** » | ⚠ **FAUX** |
| `core/provenance.py:10` | « le détecteur en place est **GPL-3.0 + Manga109-s** » | ⚠ **ambigu** — il y a deux détecteurs |

`manga/models.py:39-47` est sans ambiguïté et l'était déjà : Manga109-s concerne
`mayocream/comic-text-detector` (le texte sur le dessin), pas
`kitsumed/yolov8m_seg-speech-bubble` (les bulles).

⚠ **Les deux premières lignes ne se contredisent pas** — elles ne répondent pas à la même
question. La page du modèle *déclare* GPL-3.0 ; les poids *sont* un export YOLOv8-seg, et
Ultralytics YOLOv8 est AGPL-3.0. Les deux faits comptent pour qui rediffuse. Le lot les écrit
tous les deux plutôt que d'arbitrer en silence.

### 1.2 Pourquoi c'est plus grave qu'une incohérence de commentaire

Ces phrases sont **affichées**. `gui/sondes.py:175` est le remède montré sur la page d'accueil
quand les poids manquent ; `manga/doctor.py:85` documente le verdict que la page Diagnostic
rend. Quelqu'un qui s'apprête à télécharger un fichier sous une licence qui n'est pas celle du
projet lisait donc une licence **fausse**, et on lui demandait ensuite de vérifier avant de
rediffuser ses planches.

### 1.3 Après

| Grandeur | Avant | Après |
|---|---:|---:|
| endroits qui **déclarent** une licence de poids | 4 (`reparations`, `sondes`, `doctor`, `dialogues`) | **1** (`manga/models.py`) |
| endroits qui **affichent** une licence | 4 | 4, mais tous par lecture |
| mentions de Manga109-s attachées au détecteur de bulles | **3** | **0** |
| licences portant leur date de relevé | 1 sur 3 | **3 sur 3** |

`tests/test_licences_poids.py` (15 tests) refuse désormais qu'une licence soit réécrite dans un
module d'affichage, et que « Manga109 » réapparaisse à côté du détecteur de bulles.

⚠ **Ce que ce test NE dit PAS** : que les licences sont **justes**. Aucun test ne peut lire une
page Hugging Face. Il dit qu'elles sont dites à un seul endroit, avec leur date. La justesse
reste une vérification humaine, et sa date est celle du relevé — pas celle du jour.

---

## 2. La licence atteignait-elle l'utilisateur ? Non, et c'était mesurable

`gui/vue_diagnostic.phrase_geste()` rendait `verdict.geste` **en priorité** :

```python
if verdict.geste:
    return verdict.geste
reparation = rep.par_identifiant(...)      # ← la seule branche qui écrit la licence
if reparation is not None:
    return reparation.consigne()
```

Or **tous** les verdicts réparables des doctors portent un `geste`. La seconde branche n'était
donc **jamais atteinte en production**. Relevé :

| Où la licence apparaissait | Quand |
|---|---|
| infobulle du bouton (`gui/diagnostic.py:93`) | au survol, jamais à la lecture |
| boîte de confirmation (`gui/fenetre.py:902`) | **après** le clic |
| corps de la page | ⚠ **nulle part** |

Et le geste de `poids_detection` (`manga/doctor.py:101-103`) **promettait** : « la page
Diagnostic le fait d'un bouton, licence affichée avant » — sans jamais nommer la licence.

**Après** : `phrase_licence()` s'ajoute à côté de `phrase_geste()` — le geste dit quoi faire, la
licence dit sous quelles conditions. Les confondre reviendrait à choisir laquelle des deux on
n'affiche pas.

---

## 3. Deux réparations sur quatre étaient inatteignables

`core/reparations.py` déclare quatre réparations `RECUPERABLE`. `bouton_pour()` exige un
`Verdict` qui les nomme :

| Réparation | Verdict qui la nomme | Atteignable avant ? |
|---|---|---|
| `poids_detection` | `manga/doctor.py:_section_detecteur` | oui |
| `polices` | `manga/doctor.py:_section_police` | oui |
| `poids_texte` | **aucun** | ⚠ **non** |
| `modele_ocr` | **aucun** | ⚠ **non** |

Le catalogue les déclarait automatiques, avec leur URL, leur taille, leur empreinte et leur
geste — et **rien, nulle part, ne pouvait les déclencher**.

### 3.1 La correction n'est pas d'ajouter deux verdicts

⚠ Et c'est délibéré. La sortie console de `run_manga.py --check` est un contrat scripté, gelé
octet pour octet par `tests/test_core_diagnostic_iso.py` ; deux sections de plus la
casseraient. Surtout, ce n'est pas ce qu'on cherche : **télécharger un poids est un geste, pas
une réparation d'erreur**, et un verdict n'existe précisément que lorsqu'il y a un problème.

D'où un bloc **« Poids et modèles »** permanent, qui liste les quatre avec leur licence, leur
taille, leur état et un bouton — **visible sans qu'aucun diagnostic ait tourné**.

### 3.2 L'état affiché, et celui qu'on refuse d'inventer

| Réparation | État mesurable ? | Pourquoi |
|---|---|---|
| `poids_detection`, `poids_texte` | **oui** | Angelith pose le fichier, à un chemin que `config.yaml` nomme |
| `modele_ocr` | **non** | le cache de `huggingface_hub`, dont ce projet n'est pas propriétaire |
| `polices` | **non** | le registre de polices de Windows |

Pour les deux derniers, la page affiche « état non mesuré » et **garde le bouton** : récupérer
un modèle déjà présent est idempotent, alors que masquer le bouton laisserait sans recours
quelqu'un dont le cache est corrompu.

⚠ Afficher « présent » ou « absent » pour ces deux-là aurait été un verdict que personne n'a
mesuré — exactement ce que la règle des chiffres du dépôt refuse.

---

## 4. Compiler — de cinq commandes à une

### 4.1 Avant

`docs/COMMANDES.fr.md` listait **cinq** commandes à recopier dans le bon ordre, et rien ne les
enchaînait. Le coût s'est vu au lot précédent : **l'installeur mesuré du lot 37 porte 2.30.0
alors que le dépôt était en 2.31.0**, faute d'avoir régénéré `installeur/version.iss` avant de
compiler (`docs/mesures/empaquetage-2026-09-06.md` §4).

### 4.2 Un défaut trouvé par la première exécution de l'outil

```
$ python tools/geler.py --outils
❌ PyInstaller introuvable
   → pip install pyinstaller
✓ Inno Setup (ISCC) — C:\Users\<nom>\AppData\Local\Programs\Inno Setup 6\ISCC.exe
```

⚠ **`ci.yml` cherchait Inno Setup uniquement dans `C:\Program Files (x86)\Inno Setup 6\`.** Sur
la machine principale du projet, une installation par `winget --scope user` l'a mis dans
`%LOCALAPPDATA%\Programs\`. Le job de CI aurait marché (l'image GitHub porte le premier chemin),
**la commande documentée non**. `tools/geler.py` cherche dans le `PATH` puis aux trois
emplacements connus, et **la CI l'appelle** — ce qui rend les deux chemins identiques par
construction, au lieu de les tenir en phase à la main.

### 4.3 La chaîne mesurée

`python tools/geler.py`, de bout en bout, sur la machine principale — **une seule commande** :

| Étape | Durée |
|---|---:|
| régénérer `installeur/version.iss` depuis `core/version.py` | 0,6 s |
| **geler** (PyInstaller, un dossier) | **583,6 s** |
| 1/3 — la version survit au gel | 1,6 s |
| 2/3 — le diagnostic structuré se collecte | 48,6 s |
| 3/3 — la fenêtre s'ouvre sur l'accueil, sans tome | 9,8 s |
| **construire l'installeur** (Inno Setup, `lzma2/max`) | **308,5 s** |
| empreintes SHA-256 | 0,8 s |
| **total** | **953,4 s** (15 min 53 s) |

| Artefact | Mesure |
|---|---|
| dossier gelé | **916,6 Mo**, **5 147 fichiers** |
| installeur | **292,1 Mo** |
| empreinte publiée | `72a795885ccfc37bef8daa500ff7c3e24f586ccbac4b0da0e133caeb2ae32670  Angelith-2.31.0-windows-x64-setup.exe` |

⚠ **Le numéro de version est le bon.** L'installeur produit s'appelle
`Angelith-2.31.0-windows-x64-setup.exe`, alors que celui mesuré au lot 37 portait **2.30.0** —
c'est exactement le défaut que l'enchaînement corrige, et la première exécution de l'outil le
démontre plutôt que de le promettre.

⚠ **Les deux étapes qui coûtent sont le gel et la compression** (892,1 s des 953,4 s, soit
**93,6 %**). Les trois vérifications, elles, coûtent **60,0 s au total** — 6,3 % du temps pour
attraper les trois pannes classiques du gel. C'est le rapport qui rend le job de CI défendable.

⚠ **Ce que cette mesure ne dit pas** : elle a tourné dans l'environnement de développement de
la machine principale, qui porte plus de paquets que le jeu livré, et sur un cache disque chaud.
Le poids et le nombre de fichiers sont ceux de CE jeu, ce jour-là.

### 4.4 Ce que l'outil refuse de faire

Il **n'installe rien** — ni PyInstaller, ni Inno Setup. `pyinstaller` n'est déclaré ni dans
`pyproject.toml` ni dans un `requirements-*.txt`, et c'est délibéré : un empaqueteur n'est pas
une dépendance de ce qu'il empaquette. L'outil dit la commande et s'arrête, comme
`core/reparations.py` pour les logiciels système. `tests/test_empaquetage.py` refuse tout appel
de sous-processus à un gestionnaire de paquets.

Il **ne choisit pas non plus le jeu de dépendances**. Ce qui est gelé est ce que
l'environnement courant porte — un outil qui installerait des paquets pour geler produirait un
binaire différent de celui qu'on a testé.

---

## 5. La sonde `.cbr` — le seul report de la série 31-37 qu'un lot livré aurait dû fermer

`docs/mesures/bibliotheque-2026-09-05.md:382-385` écrivait : « La sonde définitive appartient au
`PLAN-36` L36.1, **qui n'est pas livré** […] elle est écrite pour être **remplacée** par la
sienne. »

Le `PLAN-36` a été livré en **2.30.0**. Le rebranchement, lui, n'a pas eu lieu :
`gui/depot_guide.py` gardait ses deux `shutil.which`, son propre texte de remède, et son
avertissement disant que le lot 36 n'était pas livré — **au 2026-09-06, soit une version plus
tard**.

C'est fait. `outil_rar()` appelle `core.diagnostic.verdict_outil_externe()` — qui était du
**code mort**, sans appelant en production — et lit son remède dans `core/reparations.py`, là où
la page Diagnostic le lit.

⚠ **Le point n'est pas l'économie de trois lignes**, c'est qu'il y avait deux textes pour le
même manque. C'est exactement ce qui est arrivé aux licences de poids (§1), et c'est le même
correctif.

---

## 6. Affirmations d'état levées (règle §5 bis)

| Fichier | Ce qu'il affirmait | État |
|---|---|---|
| `.github/workflows/publication.yml:13-20` | « Aucun empaquetage » ; « le projet n'est pas empaqueté et ne veut pas l'être ; c'est la raison de l'absence de `pyproject.toml` » | **périmé depuis la 2.31.0** — levé par un bloc daté. Ce qui tient de la seconde est sa conclusion (pas de PyPI), avec un motif neuf |
| `docs/roadmap.md:26` | « Current released version: **2.30.0** » | corrigé en 2.31.0 |
| `gui/depot_guide.py:36-39` | « la sonde définitive appartient au `PLAN-36`, qui n'est pas livré » | levé — cf. §5 |
| `manga/doctor.py:85`, `gui/sondes.py:175`, `core/provenance.py:10` | licence du détecteur | levé — cf. §1 |

⚠ **Un manque nommé, non corrigé par ce lot** : `publication.yml` crée une release **sans aucun
fichier** (pas de `files:`), et le job `artefact` téléverse des artefacts de *workflow*, qui ne
sont pas des assets de release. Une mise à jour automatique n'aurait rien à télécharger. C'est
le prérequis du lot 40, et il est écrit dans l'en-tête du fichier plutôt que découvert plus
tard.

---

## 7. Les critères du lot, un par un

| # | Critère | Verdict |
|---|---|---|
| 1 | compiler tient en une commande, vérifications comprises | **tenu** — `tools/geler.py`, §4 |
| 2 | la CI appelle l'outil au lieu de réécrire la séquence | **tenu** — et cela a corrigé le chemin d'Inno Setup |
| 3 | une seule source de vérité pour les licences de poids | **tenu** — `manga/models.py`, §1.3 |
| 4 | Manga109-s n'est plus attribué au détecteur de bulles | **tenu**, et gardé par un test |
| 5 | chaque licence porte sa source et sa date | **tenu** |
| 6 | la licence est visible dans le corps de la page | **tenu** — §2 |
| 7 | les quatre poids sont atteignables d'un bouton | **tenu** — §3 |
| 8 | l'état d'un poids n'est jamais inventé | **tenu** — §3.2 |
| 9 | la sonde `.cbr` est rebranchée sur celle du lot 36 | **tenu** — §5 |
| 10 | les affirmations périmées sont levées par un bloc daté | **tenu** — §6 |
| 11 | `ruff check .` passe ; boucle courte verte ; compte publié avec son dénominateur | **tenu** — §8 |
| 12 | ce document reprend les critères un par un | **tenu** — cette section |

---

## 8. Ruff, tests, compte

- `ruff check .` : **passe**.
- `python -m pytest -q -m "not modeles and not lent"` : **passe**.
- Compte de tests, toutes dépendances optionnelles installées :

| | avec PySide6 | sans PySide6 | écart |
|---|---:|---:|---:|
| avant le lot 38 (`c8ea3c5`) | 4 846 | 4 430 | 416 |
| **après le lot 38** | **4 886** | **4 470** | **416** |

Le lot ajoute **40 tests**, **collectés dans les deux configurations** : l'écart de 416 est donc
inchangé, et c'est une mesure des deux côtés, pas une déduction.

⚠ Les tests Qt de `tests/test_gui_poids.py` sont collectés **même sans PySide6** et se
**sautent** à l'exécution (`pytest.importorskip` dans la fixture, pas au niveau du module).
C'est un écart avec `tests/test_gui_diagnostic.py`, qui n'est pas collecté du tout sans Qt —
et c'est délibéré : le dépôt répète qu'« un test non collecté ne se voit nulle part ». Un test
sauté, lui, se compte.

---

## 9. Ce que ce document ne dit pas

- **rien sur la justesse des licences.** Le lot les rend cohérentes et datées, il ne les vérifie
  pas à la source — cela demande d'ouvrir deux pages Hugging Face, et la date du relevé est
  celle qui figure dans le texte, pas celle d'aujourd'hui ;
- **rien sur un vrai téléchargement depuis le nouveau bloc.** Les quatre boutons émettent bien
  l'identifiant de leur réparation (testé), et le chemin de récupération lui-même est celui du
  lot 36, inchangé — mais aucun des trois boutons neufs n'a été cliqué contre le réseau réel
  dans ce lot ;
- **rien sur l'ergonomie de la page.** Le bloc « Poids et modèles » ajoute quatre cartes en bas
  d'une page qui en portait déjà une quinzaine. Personne ne l'a utilisé en conditions réelles ;
- **rien sur le gel dans un environnement PROPRE.** La chaîne a tourné dans l'environnement de
  développement de la machine principale, qui porte plus de paquets que le jeu livré ;
- **rien sur la CI.** Le job `artefact` ne tourne que sur un tag, et aucun tag n'existe encore
  (`git tag` s'arrête à `v1.0.0`). Ses étapes ont été rejouées à la main ici, pas sur un runner.
