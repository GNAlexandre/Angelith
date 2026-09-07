# Empaquetage — mesure du 2026-09-06 (lot 37, 2.31.0)

> **Machine** — PC principal, Windows 11 Pro 26200, Python 3.12.3, PyInstaller 6.22.2,
> Inno Setup 6.7.3. **Commit de départ** : `aa74e57` (2.30.0).
> **Empreinte SHA-256 de `config.yaml`** : `77cb4bf311ae…` avant le lot,
> `f879ce66ff58…` après. Un seul changement : une section `maj:` de trois clés, **désarmée**
> (§7). Aucun cache invalidé, `manga/checkpoints.py:FORMAT_VERSION` reste à 3.
>
> Ce document reprend **les seize critères du `PLAN-37` un par un** (§8) et dit à chaque fois ce
> que la mesure ne dit pas. **Deux critères ne sont pas pleinement tenus** : le n° 11 — le taux
> antivirus multi-moteurs n'est pas mesuré (§6.1) — et le n° 13 — le job de CI existe et ses
> trois vérifications ont été rejouées à la main, mais il n'a jamais tourné sur un runner
> GitHub, faute de tag. Un troisième, le n° 5, est tenu **avec un changement de comportement
> qu'il faut lire** (§8).

---

## 1. Étape 0.1 — le poids réel, par jeu de dépendances

Quatre venv **propres**, créés et pesés par un script, sur la machine principale. Le tableau
gelé est produit par `pyinstaller angelith.spec` depuis chacun d'eux.

| Jeu | Contenu | venv | fichiers du venv | gel (onedir) | fichiers du gel | `--version` | jusqu'à la 1re fenêtre |
|---|---|---:|---:|---:|---:|---:|---:|
| **A** | socle + GUI | 755,1 Mo | 10 405 | 194,7 Mo | 284 | 0,44 s | **ne démarre pas** |
| **B** | A + détection + OCR latin | 1 003,2 Mo | 13 167 | 390,1 Mo | 356 | 0,43 s | 7,53 s |
| **C** | B + `manga-ocr` (donc torch) | 1 983,4 Mo | 39 259 | 916,5 Mo | 5 262 | 0,46 s | 7,64 s |
| **D** | C + scan | **1 983,4 Mo** | **39 259** | *non gelé* | — | — | — |

Méthode : `--version` et l'ouverture de fenêtre sont la **médiane de 5 lancements**, chronomètre
autour du processus entier (démarrage, travail, sortie), `QT_QPA_PLATFORM=offscreen`,
`ANGELITH_DONNEES` et `ANGELITH_DOCUMENTS` pointés sur des dossiers d'essai. Cache disque chaud.

### 1.1 ⚠ Le jeu D n'existe pas — le plan demandait quatre jeux, il y en a trois

`requirements-scan.txt` annonçait « sous-ensemble strict de `requirements-manga.txt` ». C'est
vrai **à l'octet près** : les jeux C et D rendent la même liste de **72 paquets**, la même
taille et le même nombre de fichiers. La prémisse du plan — quatre jeux à peser — est donc
fausse, et `tests/test_pyproject.py` la fixe désormais comme propriété
(`test_scan_est_un_sous_ensemble_strict_de_manga`).

### 1.2 ⚠ Le jeu A n'est pas un produit — il ne démarre pas

Le gel du jeu A pèse 194,7 Mo et **échoue au lancement** :

```
File "manga\checkpoints.py", line 29, in <module>
ModuleNotFoundError: No module named 'numpy'
```

`gui/fenetre.py` importe `manga/etat_planches.py`, qui importe `manga/checkpoints.py`, qui
importe `numpy` au niveau du module. Un paquet « socle + interface » n'existe donc pas : le
plancher réel de l'interface graphique est le jeu B. Le chiffre de 194,7 Mo reste publié parce
qu'il donne le coût de PySide6 seul, mais il ne désigne aucune forme livrable.

### 1.3 Ce que chaque marche coûte

| Marche | Δ venv | Δ fichiers venv | Δ gel | Δ fichiers gel |
|---|---:|---:|---:|---:|
| A → B (`numpy`, `onnxruntime`, `rapidocr`, `rarfile`) | +248,1 Mo | +2 762 | +195,4 Mo | +72 |
| B → C (`manga-ocr`, donc `torch` + `transformers`) | **+980,2 Mo** | **+26 092** | **+526,4 Mo** | **+4 906** |

⚠ **Le nombre de fichiers est la grandeur que ce lot a sous-estimée**, pas le poids. Le gel
passe de 356 à 5 262 fichiers — **×14,8** — et c'est ce que paient l'installeur (231,9 s de
compression) et la désinstallation, pas les mégaoctets.

### 1.4 ⚠ Ce que ce tableau ne dit pas

- **rien du disque froid.** Les temps sont ceux d'un cache chaud, ce qui est le cas normal mais
  pas le pire ;
- **rien de la fenêtre visible.** `offscreen` ne peint pas ; le coût réel de la première
  peinture sur un écran DPI élevé n'est pas compté ici ;
- **rien de la variance entre machines.** Une médiane de cinq lancements sur **une** machine
  n'est pas une distribution ;
- **la ligne « jusqu'à la 1re fenêtre » compte le processus entier**, y compris sa sortie. La
  part interne, de `QApplication` à `show()`, est de **0,10 s** — donc les 7,5 s sont
  essentiellement du chargement de Qt et l'analyse des 158 Ko de `config.yaml`, pas du dessin.
  Deux chiffres, deux dénominateurs, et il faut les deux.

---

## 2. Étape 0.2 — la forme du produit, tranchée

### 2.1 Combien des œuvres sont exploitables sans OCR japonais

Relevé par `tools/inventaire_oeuvres.py` sur le corpus réel (18 œuvres, 55 tomes). La règle
appliquée : le light novel n'appelle **aucun** OCR (extraction de texte par `pymupdf` /
`python-docx`) ; le manga et le webtoon n'appellent `manga-ocr` que sur source japonaise (le
latin passe par `rapidocr`) ; la brique scan est de l'OCR japonais par construction.

| | tomes | œuvres |
|---|---:|---:|
| exploitables **sans** `manga-ocr` | **27 / 55** | **13 / 18** |
| exigent `manga-ocr` | 28 / 55 | 5 / 18 |

Détail : 26 light novels (toutes langues source confondues, japonais compris) + 1 webtoon
anglais d'un côté ; 26 mangas japonais, 1 tome manga + scan, 1 tome scan de l'autre.

⚠ **Le chiffre qui décide n'est pas 27 sur 55, c'est « zéro manga ».** Un paquet sans
`manga-ocr` ne sert pas la brique que le dépôt déclare **stable** et sur laquelle reposent ses
mesures les plus solides (257 planches sur 258 en numérotation complète). Il servirait la brique
light novel — également stable — et un webtoon.

### 2.2 Les deux voies « on l'installera après » : essayées, et elles échouent

Le plan demandait de les **essayer avant de choisir**. Fait, le 2026-09-06 :

**Voie 1 — `pip` dans le paquet gelé.** Un exécutable PyInstaller n'est pas un interpréteur :

```
$ angelith-console.exe -m pip install manga-ocr
angelith-gui: error: unrecognized arguments: -m pip install manga-ocr
```

Il n'y a pas de `-m`, pas de `pip`, pas de `site-packages`. La phrase « il suffira d'installer
le paquet après » ne survit pas à l'essai, exactement comme le plan le soupçonnait.

**Voie 2 — une extension préparée, déposée dans le paquet.** Les 18 paquets de `manga-ocr` et
ses dépendances ont été copiés depuis le venv C dans le `_internal/` du gel B (1,4 Go au total).
Le diagnostic du binaire rend alors :

```
bloquant  pip_manga_ocr  le paquet Python « manga-ocr » n'est pas importable
                         (No module named 'timeit')
```

Le gel n'embarque que la part de la bibliothèque standard que **l'application** utilise ;
`torch` en demande davantage. Distribuer une extension exigerait donc de la construire contre la
fermeture exacte de chaque gel, et de la reversionner à chaque livraison. Ce n'est pas
impossible, c'est un lot.

### 2.3 La décision

> **Un seul paquet, complet — le jeu C, `manga-ocr` compris.**

Motifs, dans l'ordre :

1. les deux formes « paquet léger + OCR ajouté ensuite » sont **mesurées impossibles** avec
   cette chaîne (§2.2). L'option n'existe pas, elle n'a donc pas à être arbitrée ;
2. un paquet léger ne traiterait **aucun manga** (§2.1), c'est-à-dire aucune des œuvres pour
   lesquelles le dépôt a ses meilleures mesures ;
3. le coût est connu et il est acceptable pour un logiciel de bureau : **916,5 Mo** de dossier
   gelé, **291,1 Mo** d'installeur compressé.

⚠ **Ce que cette décision coûte, écrit plutôt que tu** : quelqu'un qui ne traduit que des light
novels télécharge 291 Mo dont il n'utilisera jamais `torch`. Le paquet léger est mesuré (390,1 Mo
gelés) et se reconstruit en retirant `requirements-manga.txt` d'une ligne du job de CI ; le
chiffre à lui opposer est celui des 27 tomes sur 55.

---

## 3. Étape 0.3 — ce que l'installation ne contient pas

Écrit **avant** de commencer, et devenu le texte de l'écran 1 de l'installeur
(`installeur/avant-installation.txt`, `InfoBeforeFile`) :

| Absent | Motif |
|---|---|
| poids de détection de bulles | GPL-3.0 + Manga109-s — non redistribuable |
| modèle de langue | Ollama / LM Studio s'installent séparément |
| modèle d'OCR | récupéré depuis sa source, avec consentement (~424 Mo) |
| Pandoc, WeasyPrint, `unrar`, ComfyUI | outils système, hors périmètre |
| toute œuvre | le tome de démonstration du lot 36 est synthétique |

`tests/test_empaquetage.py::test_la_page_d_information_dit_ce_qui_n_est_pas_livre` garde cette
liste : elle ne peut plus disparaître de l'écran 1 sans faire tomber un test.

---

## 4. L'installeur, construit et exécuté

| Grandeur | Mesure |
|---|---|
| fichier | `Angelith-2.30.0-windows-x64-setup.exe` |
| taille | **291,1 Mo** (contre 916,5 Mo de dossier gelé) |
| SHA-256 | `f2e40d494471b58b5191347c655884c1c8c3a7d5aeff0d88dc4f263e64f578c8` |
| temps de compilation | 231,9 s (`lzma2/max`, `SolidCompression`) |
| installation silencieuse au dossier par défaut | **code 0**, sans UAC |
| ce qui est installé | 922,2 Mo, 5 264 fichiers |
| l'application installée s'ouvre | oui — accueil, aucun tome, 0,149 s |
| désinstallation silencieuse | **code 0**, le dossier d'installation disparaît |

> ⚠ Le numéro de version du binaire construit est **2.30.0** et non 2.31.0 : l'installeur a été
> compilé avant le bump de version de la livraison. `installeur/version.iss` est régénéré depuis
> `core/version.py`, et la règle 5 de `tools/verifier_livraison.py` refuse désormais un
> `core/version.py` qui bouge sans lui. La CI reconstruira au tag, avec le bon numéro.

### 4.1 La désinstallation ne touche à aucune donnée — vérifié par exécution

Cinq fichiers témoins posés avant la désinstallation, tous **présents après** :

```
%LOCALAPPDATA%\Angelith\config.yaml
%LOCALAPPDATA%\Angelith\.angelith-essai
%LOCALAPPDATA%\Angelith\manga_models\bubble_detector.onnx
Documents\Angelith\build\Essai\tome.md
Documents\Angelith\sources\Essai\planche.txt
```

La boîte « supprimer aussi mes réglages » a `MB_DEFBUTTON2` : sous `/SUPPRESSMSGBOXES`, elle
répond **Non**. C'est le comportement voulu — quelqu'un qui valide sans lire garde ses réglages.

### 4.2 ⚠ Un défaut trouvé en chemin : la longueur de chemin de Windows

La **première** installation d'essai a **échoué**, dans un dossier profond :

```
Defaulting to Abort for suppressed message box (Abort/Retry/Ignore):
  …\essai-install\_internal\torch-2.14.0.dist-info\licenses\third_party\flash-attention\…
User canceled the installation process.
```

Mesuré : le chemin relatif le plus long du gel fait **131 caractères**
(`_internal\torch-2.14.0.dist-info\licenses\third_party\flash-attention\third_party\aiter\3rdparty\composable_kernel\docs\license.rst`),
et il vient entièrement de `torch`. Le dossier par défaut
(`%LOCALAPPDATA%\Programs\Angelith`, 46 caractères) donne un total de **178 sur les 260** de
`MAX_PATH` : il reste **82 caractères** de marge pour un dossier choisi par l'utilisateur.

⚠ **C'est un vrai mode de panne**, pas une curiosité de test : quelqu'un qui installe dans un
chemin profond voit l'installation s'interrompre. Il n'est **pas corrigé par ce lot** — le
corriger demanderait soit d'exclure les licences tierces de `torch` du gel (donc de retirer des
textes de licence d'un paquet redistribué, ce qu'on ne fait pas), soit d'activer le support des
chemins longs, qui est un réglage système. Il est écrit ici, et c'est le premier pas.

---

## 5. Les trois pannes du gel — rencontrées, pas imaginées

Le job de CI vérifie trois choses sur le binaire. Les trois ont réellement échoué pendant ce
lot, dans cet ordre :

1. **la sortie perdue.** `--verifier-demarrage` sur le binaire **fenêtré** n'écrivait rien et ne
   sortait jamais : sous Windows, un binaire lié en sous-système « fenêtre » n'a pas de sortie
   standard, et une exception non rattrapée y ouvre une boîte de dialogue que personne ne clique.
   D'où `angelith-console.exe`, le même programme lié en console, que la CI pilote ;
2. **un import manquant.** Le gel du jeu A est mort sur `No module named 'numpy'` (§1.2) — un
   défaut de périmètre de dépendances, invisible dans le dépôt ;
3. **une ligne perdue au déménagement.** Le corps de `main` a quitté `gui.py` pour
   `gui/lancement.py`, et `cli.configurer_stdout()` — qui était à l'import de `gui.py` — n'a pas
   suivi. Le gel a rendu le verdict immédiatement :
   `UnicodeEncodeError: 'charmap' codec can't encode character '⚠'`, au premier « ⚠ » du
   JSON, sur une console cp1252. Corrigé, avec le commentaire qui dit pourquoi l'appel est à
   l'import et non dans `main`.

Et une quatrième, qui n'est pas une panne du gel mais du protocole : `transformers` **écrit un
avertissement sur la sortie standard** avant le premier octet du JSON. La sortie machine de
`--diagnostic-json` accepte donc un fichier, et `tools/verifier_gel.py` lit la dernière ligne
JSON plutôt que le fichier entier.

⚠ **Aucune de ces quatre n'aurait été trouvée par la suite de tests du dépôt.** C'est l'argument
du job de CI, et il est maintenant chiffré : quatre défauts pour un premier gel.

---

## 6. Le comportement antivirus, avec sa date

**Windows Defender, 2026-09-06** — moteur `1.1.26080.3`, signatures `1.459.74.0` du
**2026-09-06 02:38**, protection en temps réel active. `MpCmdRun.exe -Scan -ScanType 3` :

| Cible | Verdict |
|---|---|
| dossier gelé, jeu B (390,1 Mo, 356 fichiers) | **found no threats** |
| dossier gelé, jeu C (916,5 Mo, 5 262 fichiers) | **found no threats** |
| installeur (291,1 Mo, non signé) | **found no threats** |

### 6.1 ⚠ CRITÈRE NON TENU — le taux multi-moteurs n'est pas mesuré

Le plan demande « un taux n moteurs sur m ». Il n'est **pas** mesuré, et le motif est une
décision, pas un oubli : soumettre un binaire à VirusTotal le **publie** dans un dépôt
d'échantillons consultable par des tiers, de façon permanente. C'est une décision de publication
qui appartient au mainteneur ; elle a été posée et **déclinée** le 2026-09-06.

Conséquence à ne pas masquer : **on ne sait pas** comment les autres moteurs réagissent à ce
binaire. Le « 0 menace » ci-dessus vaut pour Defender, à cette date, sur cette machine, et pour
rien d'autre.

### 6.2 La décision de signature, écrite

> **Aucun certificat au 2026-09-06 ; l'avertissement est documenté.**

- **certificat acheté** : écarté pour l'instant. Un certificat OV coûte de l'ordre de la centaine
  d'euros par an et un EV davantage — et aucune mesure de ce lot ne dit que le projet a des
  utilisateurs à qui l'épargner. ⚠ *Ce chiffre est un ordre de grandeur de marché, pas une
  mesure de ce dépôt* : la règle des chiffres impose de le dire ;
- **recompilation du chargeur PyInstaller** : non tentée. Le remède vise un binaire signalé ;
  Defender ne signale rien, il n'y a donc rien à mesurer. Si un signalement apparaît, c'est le
  premier geste, et il se mesure avant de se supposer ;
- **signalement de faux positif** : sans objet aujourd'hui, même motif ;
- **avertissement documenté** : **retenu**. `installeur/avant-installation.txt` annonce
  SmartScreen à l'écran 1, explique le geste (« Informations complémentaires » puis « Exécuter
  quand même ») et renvoie aux empreintes SHA-256 publiées avec chaque release.

⚠ **Aucun contournement d'heuristique n'a été écrit, tenté ni envisagé.** `--onefile` est refusé
et UPX désactivé — deux décisions qui vont *dans le sens* des heuristiques, pas contre elles.

---

## 7. `config.yaml` dans une installation — les trois pièges

| Piège | Ce qui est livré | Test |
|---|---|---|
| 1. la copie est écrasée à la mise à jour | `installer_config_utilisateur()` ne crée que si absent, par `shutil.copy2` | `test_la_copie_n_est_jamais_remplacee` |
| 2. l'utilisateur ne voit pas les clés neuves | `ecart_de_config()` les **nomme**, sans fusionner | `test_une_cle_ajoutee_par_la_mise_a_jour_est_nommee` |
| 3. les œuvres dans le dossier d'installation | `ancrer_chemins()` → `Documents\Angelith` | `test_en_gel_aucun_chemin_d_oeuvre_ne_tombe_dans_l_installation` |

**Vérifié sur le binaire gelé** : le diagnostic du gel rend `config` =
`…\donneesB\config.yaml` — la copie utilisateur, créée au premier lancement —, et
`chemin_sources` pointe vers le dossier de **documents**, pas vers le paquet.

`config.yaml` n'est **jamais** réécrit : `test_le_config_livre_n_est_jamais_reecrit` compare son
empreinte SHA-256 avant et après un cycle complet de résolution, d'ancrage et de comparaison, et
`test_la_copie_utilisateur_est_octet_pour_octet_celle_du_depot` vérifie que les 158 Ko de prose
arrivent intacts chez l'utilisateur.

⚠ **Le seul changement de `config.yaml` dans ce lot** est l'ajout d'une section `maj:` de trois
clés, **désarmée** (`verifier: false`). Rien d'autre n'a bougé, aucun cache n'est invalidé,
`manga/checkpoints.py:FORMAT_VERSION` reste à 3.

---

## 8. Les seize critères du plan, un par un

| # | Critère | Verdict |
|---|---|---|
| 1 | tableau de poids publié pour les quatre jeux | **tenu**, avec une correction : il n'y a que **trois** jeux distincts (§1.1), et le jeu A ne démarre pas (§1.2) |
| 2 | forme tranchée par écrit, essai des options publié | **tenu** — §2.3, et les deux essais qui écartent les options 2 et 3 sont publiés (§2.2) |
| 3 | `pyproject.toml`, version dynamique, test des métadonnées | **tenu** — `tests/test_pyproject.py` |
| 4 | l'affirmation de `core/version.py` levée par un bloc daté | **tenu** — et le même geste appliqué à `ruff.toml`, `.coveragerc` et `requirements-dev.txt`, qui portaient la même |
| 5 | les cinq `requirements-*.txt` fonctionnent ; iso ou dit | **tenu, avec un changement dit** — ils deviennent des enveloppes `-e .[extra]`. Ce qui change : `pip install -r` installe aussi `angelith` en éditable, et **doit être lancé depuis la racine du dépôt** (un `-e .` se résout contre le répertoire courant). Vérifié dans un venv propre : les six points d'entrée s'installent et répondent |
| 6 | onedir, refus d'onefile motivé, exclusions justifiées **et vérifiées par un lancement** | **tenu** — le motif est dans le `.spec`, les exclusions Qt viennent d'un relevé mécanique des imports, et `--verifier-demarrage` les vérifie sur le binaire |
| 7 | une seule fonction résout les chemins ; un test échoue sur un `__file__` résiduel | **tenu** — `core/installation.py:ressource()`, `tests/test_installation_chemins.py` |
| 8 | `config.yaml` résolu CLI → utilisateur → livré, jamais réécrit, écart signalé | **tenu** — §7 |
| 9 | `chemins.sources` / `chemins.build` hors du dossier d'installation | **tenu** — §7, et les **poids** aussi, qui n'étaient pas dans le critère |
| 10 | installeur par utilisateur, sans UAC, version depuis `core/version.py`, désinstallation qui préserve les données | **tenu, vérifié par exécution** — §4 et §4.1 |
| 11 | antivirus mesuré et publié avec sa date ; décision de signature écrite | **partiellement tenu** — Defender oui (§6), **taux multi-moteurs non mesuré** (§6.1). Décision de signature écrite (§6.2) |
| 12 | aucune vérification de version sans opt-in | **tenu** — `core/maj.py`, `verifier: false` livré, et un test qui **échouerait si un appel partait** désarmé |
| 13 | la CI produit les deux artefacts avec leurs SHA-256 et **teste le gel** | **tenu en code, non exécuté** — le job `artefact` existe, ses trois vérifications ont été **rejouées à la main** sur cette machine et sont vertes ; il n'a pas encore tourné sur un runner GitHub, faute de tag |
| 14 | pas de paquet Linux, motif écrit avec son prérequis | **tenu** — §9 |
| 15 | `ruff check .` passe, boucle courte verte, compte publié avec son dénominateur | **tenu** — §10 |
| 16 | ce document reprend les critères un par un | **tenu** — cette section |

---

## 9. Linux et macOS — hors périmètre, avec le motif

**macOS** reste « out of scope » dans `docs/roadmap.md`, faute de machine pour tester.

**Linux** n'est pas livré, et le prérequis a un nom : `PLAN-20` L20.2. La CI du dépôt a bien une
matrice `[windows-latest, ubuntu-latest]` depuis le lot 20 — mais un **paquet** Linux demanderait
en plus de valider le gel sur cette plateforme, et rien dans ce lot ne l'a fait : PyInstaller n'a
tourné que sous Windows, et `installeur/angelith.iss` est un script Inno Setup, qui n'existe pas
ailleurs.

⚠ **Ne pas livrer un paquet Linux « parce que ça marche sur ma machine ».** `docs/roadmap.md`
liste « One-click Windows/Linux packaging » comme un jalon, ce qui rend la tentation réelle. Ce
qui manque, précisément : un `.spec` exercé sur un runner Linux, un format de paquet choisi
(AppImage, Flatpak, `.deb` ?), et les trois mêmes vérifications rejouées dessus.

---

## 10. Ruff, tests, compte

- `ruff check .` : **passe**.
- `python -m pytest -q -m "not modeles and not lent"` : **passe**.
- Compte de tests — le dénominateur est celui de `docs/chiffres-de-reference.md`, toutes
  dépendances optionnelles installées :

| | avec PySide6 | sans PySide6 | écart |
|---|---:|---:|---:|
| avant le lot 37 (`aa74e57`) | 4 705 | 4 289 | 416 |
| **après le lot 37** | **4 846** | **4 430** | **416** |

Les deux colonnes ont été relevées, sur un `git worktree` propre pour la première — un
`git stash` aurait laissé les fichiers de test NEUFS en place et rendu un « avant » qui contenait
déjà l'« après ». La boucle courte en exécute **4 789**, les mêmes 57 restant désélectionnés par
`lent` / `modeles`.

Le lot ajoute **141 tests**, et **les 141 sont sans Qt** — l'écart de 416 est donc rigoureusement
inchangé, et c'est une mesure, pas une déduction. La proportion s'explique : cinq des cinq
fichiers neufs (`test_installation.py`, `test_installation_chemins.py`, `test_pyproject.py`,
`test_core_maj.py`, `test_empaquetage.py`) ne touchent pas à l'interface, et les modules neufs
(`core/installation.py`, `core/maj.py`, `tools/verifier_gel.py`, `installeur/generer.py`) sont
tous sans Qt. Seul `gui/lancement.py` en importe — et tardivement, dans `main()`, ce qui est
précisément ce qui permet à `--diagnostic-json` de tourner sans écran.

---

## 11. Ce que ce document ne dit pas

- **rien sur un vrai utilisateur.** Personne d'autre que l'auteur n'a installé ce paquet. Le
  « code 0 » d'une installation silencieuse n'est pas le même événement qu'une personne qui
  double-clique et lit un écran ;
- **rien sur SmartScreen en conditions réelles.** Le binaire n'a pas été téléchargé depuis
  Internet, donc il ne porte pas la marque du Web (`Zone.Identifier`) : l'avertissement annoncé
  au §6.2 est **déduit du fait qu'aucun certificat ne signe le binaire**, pas observé ;
- **rien sur la mise à jour d'une installation existante par une autre.** L'`AppId` est fixe et
  Inno Setup sait remplacer, mais le scénario « 2.31.0 par-dessus 2.30.0, avec un `config.yaml`
  utilisateur édité » n'a été testé qu'en unitaire, jamais avec deux vrais installeurs ;
- **rien sur les autres antivirus** (§6.1) ;
- **rien sur le temps de démarrage à froid**, ni sur une machine plus lente que celle-ci ;
- **rien sur le poids d'un `dist/` construit par la CI.** Le runner GitHub installe les mêmes
  paquets, pas nécessairement les mêmes versions : les 916,5 Mo sont ceux du 2026-09-06 sur
  cette machine, avec `torch` 2.14.0.
