# Le socle génératif — la frontière, le moteur, la trace (lot 24)

**Date** : 2026-08-29 · **Version livrée** : 2.15.0 · **Branche** : `main` · **Commit de
départ** : `781c2ff` (2.14.2)
**Empreinte SHA-256 de `config.yaml` après le lot** :
`d611609985d53c51fd8ef6b75b3acaf1d4ad9fd0b99324c78dd4e2ee5d1e9910`
**Plan exécuté** : [`docs/plans/PLAN-24-LE-SOCLE-GENERATIF.md`](../plans/PLAN-24-LE-SOCLE-GENERATIF.md)

> ## ⚠ Suite : trois de ces non-mesures ont été faites le même jour
>
> Ce document a été écrit sur une machine sans GPU ni réseau, et il le dit. **Quelques heures
> plus tard, la RX 7900 XT et le réseau étaient disponibles**, et les étapes 0.3, 0.4 et L24.5
> ont été mesurées : voir [`connecteur-qwen-2026-08-29.md`](connecteur-qwen-2026-08-29.md)
> (version 2.16.0).
>
> **Ce document n'est pas corrigé pour autant.** Il décrit fidèlement ce qui était su au moment
> de la livraison 2.15.0, et le dépôt ne réécrit pas ses mesures après coup — c'est ce qui rend
> ses documents lisibles. Les verdicts ci-dessous restent donc ceux de la 2.15.0 ; les verdicts
> à jour sont dans le document suivant.
>
> Ce que la suite a montré, en une ligne : le chemin ComfyUI tient (**103,7 s par image**, pic
> **14 417 Mio** sur 20 464, **0 échec sur 11**), les licences sont bien Apache-2.0, le rejeu
> est **bit-à-bit reproductible** — et **six défauts** que les 110 tests verts de ce lot-ci
> n'avaient pas vus sont apparus au premier usage réel.

---

## 1. Ce que ce document dit avant tout le reste

**Trois des quatre mesures que le plan demandait n'ont pas pu être faites**, et ce document
commence par là plutôt que de le glisser dans un paragraphe de fin. La session qui a exécuté
le lot n'avait **ni la 7900XT, ni accès au réseau**. Elle ne pouvait donc ni chronométrer un
modèle d'image, ni relire une licence à sa source primaire, ni mesurer la reproductibilité
d'un backend réel.

> **« Un tableau qui ne confirme jamais que le plan n'est pas une mesure. »** La réciproque
> tient aussi : un lot qui publie « ceci n'a pas été mesuré, et voici ce que le code en
> conclut » est un lot honnête ; un lot qui livre un moteur par défaut sans l'avoir chronométré
> ne l'est pas.

Ce que le lot a fait, en conséquence, est de **rendre la non-mesure visible dans le
comportement du logiciel** plutôt que dans une note de bas de page :

| Ce qui n'est pas mesuré | Ce que le code en fait |
|---|---|
| les trois chemins d'exécution sur la 7900XT | `illustration.moteur: "factice"` par défaut — un carré uni, pas une illustration |
| les licences de poids à la source primaire | **aucune URL, aucune empreinte de poids codée en dur** dans le dépôt, à l'inverse de `manga/models.py` |
| la reproductibilité d'un backend réel | `--rejouer` est livré et testé ; son verdict sur un vrai moteur reste à écrire |
| la ressemblance des personnages | rien n'est affirmé — c'est le `PLAN-25` |
| le coût **complet** de la bascule VRAM | seul le déchargement est mesuré — 2,0 s, §3.2 bis ; le reste exige le modèle d'image |

Et l'état de la brique le dit à qui lance la commande :
`ETAT_BRIQUES["illustration"] = "experimental"`, un mot **neuf** dans ce dépôt et **plus bas
que `beta`**, avec sa réserve nommée dans `core/version.py`.

---

## 2. Deux prémisses du plan corrigées par la mesure

### 2.1 — « environ 10 Go en 4 bits » : le chiffre n'est pas faux, son dénominateur manque

| Ce qu'on mesure | Valeur | Statut |
|---|---|---|
| GGUF Q4_0 / Q4_K_S du **transformeur seul** de `Qwen-Image-2512` | **11,9 – 12,3 Go** | relevé le 2026-08-27, **non revérifié** |
| GGUF Q4_K_M du transformeur seul | **13,1 Go** | idem |
| Encodeur de texte `Qwen2.5-VL-7B` | non compté ci-dessus | idem |
| VAE | non compté ci-dessus | idem |
| **VRAM résidente totale** | **aucun chiffre établi** | **jamais mesuré** |

« ~10 Go » désigne donc le **transformeur seul**, et il est **sous** la fourchette publiée.
La grandeur qui décide — la VRAM résidente — n'a de chiffre nulle part. C'est ce qui rend la
conclusion structurelle du lot non négociable plutôt que prudente :

> `docs/README.fr.md` (≈ l. 639) : « ~17 Go ne tiennent de toute façon pas dans 20 Go de VRAM.
> Ça supprime tout scénario de seconde instance / partage de VRAM. »

**La génération d'image et la traduction ne coexistent jamais en VRAM.** La bascule passe par
`core/power.py:ollama_unload` — le mécanisme **existait déjà** (le dépôt décharge le LLM avant
détection/OCR quand `DmlExecutionProvider` est actif) et il est réutilisé, pas réécrit. Elle a
lieu **une fois par run**, jamais une fois par image, et son coût est mesuré et publié à côté
du temps de génération dans le `RAPPORT.md` de la brique.

### 2.2 — Le graphe d'imports décrit par le plan est faux sur deux lignes sur cinq

Le `PLAN-24` L24.1 écrit : « `core` n'importe rien d'interne, `pipeline`→core, `manga`→core,
`scan`→core+manga, `gui`→manga+core ». Le relevé du 2026-08-29 sur l'arbre réel :

| Paquet | Ce que le plan annonce | Ce que le dépôt fait | Verdict |
|---|---|---|---|
| `core` | rien d'interne | rien d'interne | ✅ |
| `pipeline` | → core | core | ✅ |
| `manga` | → core | core **et pipeline** | ❌ **faux** |
| `scan` | → core + manga | core + manga | ✅ |
| `gui` | → manga + core | core, manga **et pipeline** | ❌ **faux** |
| `illustration` | → core | core | ✅ (exigence tenue) |

Les deux arêtes manquantes sont réelles et anciennes : `manga/glossaire_manga.py` l. 106 et
`manga/orchestrator_manga.py` l. 1396 importent `optimize_glossary_file` ; `gui/` importe
`pipeline` en six sites, tous en import tardif. **Aucune ne crée de cycle** — `pipeline`
n'importe que `core` — donc l'argument « graphe sans cycle » du dossier de financement tient,
mais il tenait sur une description approximative.

⚠ **Ce n'est pas seulement une correction de document.** Aucun test du graphe d'imports
n'existait dans `tests/` avant ce lot : la propriété avait été constatée à la main lors d'un
audit et jamais gardée. `tests/test_imports_briques.py` la protège désormais, **pour les six
paquets**, et il vérifie l'absence de cycle sur le graphe **réel**, pas sur la table déclarée.

---

## 3. Les mesures qui n'ont pas eu lieu, et pourquoi

### 3.1 — Étape 0.3 : les trois chemins d'exécution — **NON MESURÉE**

| Chemin | Secondes/image | Pic VRAM | Échecs / 20 | Statut |
|---|---|---|---|---|
| ComfyUI local (API HTTP) | — | — | — | **non mesuré** |
| `stable-diffusion.cpp` (Vulkan, GGUF) | — | — | — | **non mesuré** |
| `diffusers` en pur Python | — | — | — | **non mesuré** |

Cause : ni GPU ni réseau dans la session. **Aucun chemin n'a donc été écarté sur mesure**, et
le document ne prétend pas l'avoir fait.

**Ce qui a quand même été tranché, et ne demandait pas de GPU** : le critère de choix du plan
n'est pas la vitesse, c'est *combien de dépendance le dépôt avale-t-il ?* Cette question-là se
répond sans chronomètre, et le dépôt y a déjà répondu deux fois — OpenCV refusé pour ~60 Mo
(interdit n° 4), Ollama installé par l'utilisateur et pesant zéro dans
`requirements-*.txt`. `diffusers` est donc écarté **sur ce critère seul, et le document le
dit** : des gigaoctets de dépendance et une dette de compatibilité ROCm. Le chemin livré est un
**client HTTP** (`illustration/comfyui.py`, `urllib` uniquement, comme `core/power.py`).

⚠ **Ce client n'a jamais tourné contre un vrai serveur ComfyUI.** Sa plomberie — mise en file
sur `/prompt`, sondage de `/history`, récupération sur `/view`, erreurs, absence d'image — est
testée contre un transport factice ; son comportement réel est **inconnu**. C'est aussi
pourquoi le défaut reste `"factice"` : un utilisateur doit choisir `comfyui` explicitement.

### 3.2 — Étape 0.4 : les licences à la source primaire — **NON REVÉRIFIÉES**

Les quatre lignes du tableau du plan sont reproduites dans
[`illustration_models/README.md`](../../illustration_models/README.md) **avec leur date du
2026-08-27 et la mention « non revérifié »** sur chacune. Conséquence dans le code, et c'est
la seule qui compte :

> **Aucune URL de poids et aucune empreinte de poids n'est codée en dur dans le dépôt**, à la
> différence de `manga/models.py` qui porte `DETECTEUR_URL`, `DETECTEUR_SHA256` et
> `DETECTEUR_OCTETS`. Coder une URL aurait transformé une vérification **non faite** en fait
> acquis du code.

`illustration.poids.url` et `illustration.poids.fichier` sont vides par défaut, et
`assurer_poids` refuse un téléchargement sans URL avec un message qui **nomme la raison** :
la licence des poids se vérifie à la source primaire.

### 3.2 bis — La bascule VRAM : **une moitié mesurée, et elle a trouvé un défaut**

C'est la seule mesure de la série qui n'exigeait pas de GPU : le **déchargement** du LLM passe
par une requête HTTP à Ollama, joignable sur la machine de la session. Relevé le 2026-08-29,
`llm.base_url: http://localhost:11434/v1`, `yume-27b` chargé :

| Ce qui est appelé | Essai 1 | Essai 2 | Essai 3 |
|---|---:|---:|---:|
| `models_in_config(config) + models_in_config(config, "manga")` — **2 appels** | 4,22 s | 4,14 s | 4,05 s |
| la même liste **dédoublonnée** — 1 appel | 2,03 s | — | — |

⚠ **La différence n'est pas une optimisation, c'est un défaut trouvé en mesurant.**
`core/cli.py:models_in_config` dédoublonne **dans** une section, pas **entre** deux : la config
livrée nomme le même `yume-27b` dans `modeles.traducteur` **et** dans
`manga.modeles.manga_traducteur`. Le décharger deux fois coûte **2,0 s pour un résultat
identique**. `illustration/orchestrateur.py:_basculer_vram` dédoublonne donc par
`dict.fromkeys` — l'ordre reste déterministe pour que deux runs se comparent — et un test le
fige.

**Ce que cette mesure ne dit pas, et c'est la moitié qui manque** : le `PLAN-24` demande le
coût **complet** de la bascule — déchargement **plus** chargement du modèle d'image **plus**
rechargement final du LLM. Seul le déchargement est mesuré ; les deux autres exigent le
modèle d'image, donc la machine absente. **2,0 s est donc un plancher, pas le coût.** Le seuil
du plan — « si la bascule coûte plus que huit images, c'est la bascule qu'il faut optimiser »
— reste inapplicable tant que le prix d'une image n'est pas connu ; le mécanisme qui le
calculera est livré et publié dans le `RAPPORT.md` de chaque run.

### 3.3 — L24.5 : la reproductibilité — **MÉCANISME LIVRÉ, VERDICT NON ÉCRIT**

Le critère du plan est : « deux exécutions de la même `Requete`, même graine, même modèle, même
`config.yaml`, produisent deux PNG identiques octet pour octet — ou l'écart est mesuré et
expliqué ». Sur 5 requêtes × 3 exécutions d'un backend réel : **aucune mesure**.

Ce qui est livré à la place, et qui est ce qu'on pouvait livrer :

- `Requete.empreinte()` — SHA-256 du payload canonique. Deux requêtes de même empreinte
  **doivent** produire la même image ; un test vérifie que chaque canal, chaque scalaire et
  chaque graine change l'empreinte, sans quoi le critère ne voudrait rien dire ;
- `run_illustration.py --rejouer <image>.provenance.json` — reconstruit la requête depuis son
  sidecar, régénère, compare les SHA-256, et **dit lequel des deux cas s'est produit** ;
- le message de non-identité ne présente **pas** l'écart comme un défaut : « la plupart des
  backends de diffusion ne sont pas déterministes d'une exécution à l'autre. Mesure l'écart et
  publie-le plutôt que d'affirmer la reproductibilité. »

Sur le moteur factice, déterministe par construction, le dispositif rend **3/3 identiques** —
ce qui mesure le dispositif, pas le modèle, et le document ne fait pas semblant du contraire.

---

## 4. Ce qui est mesuré, et qui ne demandait pas de GPU

### 4.1 — La frontière tient, fichier par fichier

| Propriété | Comment elle est vérifiée | Verdict |
|---|---|---|
| `illustration/` n'importe que `core/` | analyse `ast` de chaque source **plus** un sous-processus qui vérifie qu'aucun autre paquet n'est chargé | ✅ |
| aucune écriture sur un chemin préexistant | interception de `open` / `write_text` / `write_bytes` sur un arbre témoin peuplé | ✅ **0 fichier visé** |
| un run complet laisse tout l'arbre intact | SHA-256 **par fichier**, avant et après, sur tout l'arbre témoin | ✅ **0 modifié, 0 supprimé** |
| tout ce qui est neuf est dans le dossier de la brique | même relevé, en négatif | ✅ |
| `.checkpoints/` intact | SHA-256 du dossier avant/après | ✅ |
| `RAPPORT.md` et `perf.log` du tome intacts | comparaison texte | ✅ |

⚠ **Le garde n'est pas qu'un test : il est armé pendant le run.**
`illustration/frontiere.py` remplace `open`, `io.open`, `Path.write_text/write_bytes/mkdir/
unlink`, `os.replace/rename/remove`, `shutil.move` et `Image.save` pour la durée du run et
**sur le fil courant**, et lève `EcritureHorsPerimetre` sur toute cible hors du dossier de la
brique. C'est la transposition, pour une brique entière, de ce que `paint = paint & region.mask`
fait pour un tableau numpy dans `clean.py` : l'invariant ne doit pas dépendre d'un
raisonnement.

⚠ **Et il ne prétend pas être un bac à sable.** Un sous-processus, une extension C qui appelle
`fopen`, ou un serveur HTTP distant qui écrit chez lui ne passent pas par ces fonctions
Python. La brique ne lance aucun sous-processus d'écriture ; le dire vaut mieux que de laisser
croire le contraire.

### 4.2 — Le marquage n'a pas d'interrupteur, et c'est vérifié à l'exécution

Le critère 7 demandait « qu'aucun chemin de code ne sache produire un PNG sans marquage —
c'est-à-dire que l'écriture passe par une seule fonction ». Un `grep` sur les sources aurait
suffi à le *documenter* ; il se contourne d'un `getattr`. Le lot livre donc un garde
**dynamique** :

> Tant qu'un périmètre est armé, **tout fichier d'extension image** (`.png`, `.jpg`, `.webp`,
> `.psd`…) est refusé — sauf à l'intérieur de `frontiere.ecriture_marquee()`, dont
> `marquage.ecrire` est le **seul appelant du dépôt**, ce qu'un test vérifie.

Mesuré : trois extensions testées, trois refus, aucun fichier créé ; le drapeau retombe même
quand le marquage lève ; le texte, lui, passe.

Chaque PNG produit porte ses sept champs `tEXt` (`Software`, `Generator`, `AIGenerated`,
`Seed`, `Prompt` tronqué, `SourceWork`, `Disclaimer`) et son manifeste
`<image>.png.provenance.json`, qui archive le **payload JSON exact** envoyé au moteur, canaux
compris — c'est lui qui rend `--rejouer` possible.

⚠ **C2PA : non fait, et c'est écrit.** La question était « si et seulement si une bibliothèque
acceptable existe sans traîner un SDK entier ». `c2pa-python` embarque le SDK Rust `c2pa`, et
un manifeste signé demande une **autorité de certification**, donc une identité publiée, alors
que rien de cette brique ne quitte la machine. Un `tEXt` + sidecar est un marquage lisible par
machine : **un plancher défendable, pas un idéal.**

### 4.3 — Le titre de l'œuvre n'entre nulle part

| Fichier | Porte le titre ? | Pourquoi |
|---|---|---|
| PNG (`tEXt`) | **non** — `SourceWork` est `oeuvre-<12 hexa>` | il se partage |
| `<image>.provenance.json` | **non** | il se partage avec l'image |
| `RAPPORT.md` de la brique | **non** — il porte l'identifiant local | il vit à côté des images |
| `perf.log` de la brique | **non** | idem |
| `requete.yaml` | **oui**, dans sa bannière | document de **travail**, il porte la commande à retaper, il ne se partage pas |

⚠ Et le garde **lève plutôt que de censurer** : un prompt qui nomme l'œuvre fait échouer
l'écriture avec un message qui dit quoi corriger. Retirer silencieusement le titre changerait
le prompt archivé, donc casserait le rejeu, donc mentirait sur ce qui a été envoyé au modèle.

### 4.4 — La porte humaine, et le fait qu'elle n'a pas de clé

| Cas | Comportement | Vérifié |
|---|---|---|
| `valide: false` | `RequeteNonValidee`, motif nommé, **0 PNG écrit** | ✅ |
| `valide: true` mais `validation.par` vide | `RequeteNonValidee`, **autre** motif | ✅ |
| requête validée mais incohérente | `ValueError` qui liste les incohérences, **0 PNG** | ✅ |
| une clé de config qui contournerait | **il n'y en a aucune** — un test relit `CLES_CONNUES` et échoue si une clé `illustration.*` contient « valide », « force », « automatique » ou « skip » | ✅ |

Et le sidecar porte le prompt **avant** et **après** correction humaine, avec le nom du
validateur et la date : c'est la ligne exacte qui distingue « assisté » de « généré ».

### 4.5 — Le refus explicite des canaux

`Moteur.generer` refuse tout canal non déclaré, avec le canal, le moteur **et** le motif
nommés. Mesuré sur **les cinq canaux, un par un** : chacun, retiré des canaux supportés, fait
lever `CanalRefuse` — aucun n'est ignoré en silence. Pour le client ComfyUI, la propriété est
plus forte que déclarative : **les canaux supportés sont LUS dans le workflow de
l'utilisateur**, marqueur par marqueur, et le refus arrive **avant** que le graphe ne parte sur
le réseau (vérifié : `transport.envoye is None`).

---

## 5. Les onze critères du plan, un par un

| # | Critère | Verdict |
|---|---|---|
| 1 | Phrase de portée aux trois endroits, datée, attribuée, disant qu'elle ne préjuge pas du `PLAN-22` | ✅ **tenu** — `docs/README.fr.md` sous le principe, interdit n° 3 du `00-CONTEXTE-AGENT.md`, `docs/ai-provenance.md` |
| 1 bis | Trois tests de frontière | ✅ **tenu** — et le garde est armé à l'exécution, pas seulement en test |
| 1 ter | Deux phases, `requete.yaml` persisté, phase 2 refuse `valide: false`, coût de bascule mesuré et publié | ⚠ **tenu à trois quarts** — les deux phases, l'artefact et le refus sont livrés et testés ; le **déchargement** est mesuré (2,0 s, et la mesure a trouvé un déchargement en double, §3.2 bis), mais le coût **complet** de la bascule exige le modèle d'image, donc la machine absente |
| 2 | Lecture de l'art. 50(2) écrite, datée, sourcée, signalée à confirmer | ✅ **tenu** — `docs/ai-provenance.md` et `illustration/marquage.py` |
| 3 | Trois chemins mesurés sur la 7900XT, motif d'abandon des écartés publié | ❌ **NON TENU** — aucun chemin mesuré (§3.1). Le motif d'écart de `diffusers` est publié, mais il repose sur le critère de dépendance, pas sur un chronomètre |
| 4 | Prémisse « ~10 Go » confirmée ou corrigée avec son dénominateur | ✅ **tenu — corrigée** (§2.1). Le dénominateur manquant est nommé, et la VRAM résidente reste sans chiffre |
| 5 | `illustration/` n'importe que `core/`, **et un test neuf le vérifie** | ✅ **tenu, et élargi** — `tests/test_imports_briques.py` couvre les six paquets et l'absence de cycle ; il a trouvé deux erreurs dans la description du plan (§2.2) |
| 6 | `illustration.actif: false` par défaut, `run.py` et `run_manga.py` iso-comportement, empreinte de `config.yaml` annoncée | ✅ **tenu** — empreinte en tête de ce document ; aucun fichier des deux briques n'est modifié par ce lot |
| 7 | Aucun PNG sans marquage ni sidecar. Deux tests. Le sidecar archive le payload exact | ✅ **tenu** — et le second test est dynamique plutôt que statique (§4.2) |
| 7 bis | `generer` refuse tout canal non honoré, avec motif | ✅ **tenu** — les cinq canaux testés un par un (§4.5) |
| 8 | Aucun poids, aucune image, aucun titre dans git. `git check-ignore -v` le prouve | ✅ **tenu** — `*.gguf`, `*.safetensors`, `*.ckpt`, `*.part`, `illustrations/` ajoutés **au même commit** que le module de téléchargement |
| 9 | `ETAT_BRIQUES` porte la quatrième brique, état sous `beta`, réserve nommée | ✅ **tenu** — `"experimental"`, réserve écrite dans `core/version.py`, et un test échoue si quelqu'un la fait passer en `beta` |
| 10 | `ruff check .` passe ; `pytest -q -m "not modeles and not lent"` passe **sans aucun poids** | ✅ **tenu** — 110 tests neufs, aucun ne demande de GPU ni de poids |
| 11 | Ce document reprend les critères un par un, y compris les non tenus, et dit ce que la mesure ne dit pas | ✅ **tenu** — §1, §3 et §7 |

**Deux critères sur treize ne sont pas pleinement tenus** (3 et 1 ter), pour **une seule
cause** : l'absence de la machine de mesure. Aucun des deux ne peut être tenu par une session
sans GPU, et aucun n'a été contourné en écrivant un chiffre plausible.

---

## 6. Le compte, et les fichiers

| Grandeur | Avant (2.14.2) | Après (2.15.0) |
|---|---|---|
| Tests collectés (toutes dépendances) | 3 344 | **3 454** (+110) |
| Paquets internes | 5 | **6** |
| Briques déclarées dans `ETAT_BRIQUES` | 3 | **4** |
| Points d'entrée | 3 | **4** |
| Dépendances ajoutées | — | **0** |
| Octets de poids téléchargés | — | **0** |
| Clés de `config.yaml` ajoutées | — | 21, **toutes sans effet** tant que `actif: false` |

Modules livrés : `illustration/{__init__,frontiere,moteur,requete,marquage,poids,comfyui,
orchestrateur,rapport}.py`, `run_illustration.py`, `illustration_models/README.md`.
Tests : `tests/test_illustration_{frontiere,moteur,marquage,requete,poids}.py`,
`tests/test_imports_briques.py`, et trois tests de plus dans `tests/test_version.py`.

Fichiers **modifiés** hors brique : `core/version.py`, `core/config_schema.py`, `config.yaml`,
`.gitignore`, `docs/README.fr.md`, `docs/plans/00-CONTEXTE-AGENT.md`, `docs/ai-provenance.md`,
`CHANGELOG.md`, `tests/test_version.py`. **Aucun fichier de `manga/`, `pipeline/`, `scan/` ou
`gui/` n'est touché.**

---

## 7. Ce que cette mesure ne dit pas

1. **Elle ne dit du coût de la bascule que sa première moitié.** 2,0 s est le prix du
   déchargement seul ; le chargement du modèle d'image et le rechargement du LLM ne sont pas
   mesurés. Le seuil de huit images du plan reste donc inapplicable.
1. **Elle ne dit rien de la qualité d'une image.** Aucune image n'a été produite par un modèle
   génératif dans ce lot. Les seuls PNG écrits sont des carrés unis de 64 × 64 dont la couleur
   dérive d'un SHA-256.
2. **Elle ne dit rien de la ressemblance d'un personnage**, ni de la nouveauté, ni de la
   distance de style. Ce sont les trois grandeurs du `PLAN-25`, et l'annoncer ici serait le
   genre d'affirmation que `docs/mesures/webtoon-2026-08-26.md` a dû venir démentir.
3. **Elle ne dit rien du comportement réel de ComfyUI**, ni sous ROCm/Windows, ni sur GGUF.
   Les plantages signalés par des utilisateurs restent une information de seconde main, datée
   du 2026-08-27 et non revérifiée.
4. **Elle ne dit pas que la lecture de l'AI Act est juste.** Elle dit ce qui a été lu, quand,
   où, et ce que le code en a conclu. La confirmation juridique reste à faire, et le code est
   du côté prudent : marquer toujours coûte moins que ne pas marquer une fois.
5. **Elle ne dit pas que le garde de frontière est infranchissable.** Il couvre les fonctions
   d'écriture de la bibliothèque standard et Pillow, sur le fil courant. Un sous-processus ou
   une extension C y échapperaient.
6. **Le tome témoin est synthétique.** Deux PNG de 32 × 48, une bible à deux personnages. Le
   corpus réel n'est pas redistribuable, et aucune image d'œuvre sous droits ne figure dans ce
   document — seul `Pride and Prejudice` (domaine public) l'autoriserait, et il n'y avait rien
   à montrer.
7. **Le squelette de `requete.yaml` n'est pas ce que le plan décrit à terme.** La phase 1
   assemble un prompt **déterministe** à partir des attributs cités de la bible ; c'est le
   `PLAN-26` qui fait choisir les images et rédiger le prompt par `yume-27b`. Le squelette a
   une vertu que la version LLM perdra : il se teste en CI, sans serveur.

---

## 8. L'arbitrage entre deux demandes du plan, écrit pour qu'il ne se redécouvre pas

Le `PLAN-24` L24.6 demande une section « Illustrations générées » dans le `RAPPORT.md` du tome
et des lignes dans son `perf.log`. Son critère 1 bis interdit d'ouvrir en écriture un fichier
préexistant, et exige qu'un run complet laisse **toutes** les empreintes SHA-256 préexistantes
inchangées.

**Les deux ne tiennent pas ensemble.** C'est la frontière qui gagne, parce qu'elle est la
raison d'être du lot : un garde qui a une exception n'est pas un garde. La brique écrit donc
**son propre** `RAPPORT.md` et son propre `perf.log`, dans son dossier, avec le contenu que
L24.6 demande — combien d'images, quel modèle, quelle graine, le coût de la bascule, et le
rappel qu'elles ne font pas partie de l'œuvre.

L'arbitrage est écrit à trois endroits pour ne pas se rejouer : la docstring de
`illustration/rapport.py`, celle de `illustration/orchestrateur.py`, et un test —
`test_le_rapport_du_tome_et_le_perf_log_ne_sont_pas_touches` — qui échouerait si quelqu'un
revenait à la lettre du plan sans revenir sur son critère.
