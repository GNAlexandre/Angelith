# Voir ce que le projet envoie à ComfyUI — lot 28, 2026-09-02

> **Ce que ce document mesure** : le `PLAN-28`, ses neuf critères, un par un, **y compris les
> trois qui ne sont pas tenus**. Il ne contient aucun chiffre de génération : le lot ne change
> aucune image, aucun prompt, aucun seuil, aucun format de sortie.
>
> **Version livrée** : `2.22.0`. Commit de départ : `f15792a` (2.21.0).
> Empreinte SHA-256 de `config.yaml` : `ae2de92caa123b44dab956a682e3975db5c16836c53f35f10a08fab415b834a7`
> — **inchangée depuis la 2.21.0**, aucune clé n'a été ajoutée par ce lot.

---

## 1. ⚠ La prémisse qui a lâché la première : cette session a tourné sur le PC SECONDAIRE

Le plan l'écrit en tête, et il avait raison de l'écrire :

> ⚠ Ce plan se lance sur le **PC PRINCIPAL**. Il n'a aucun sens sur le secondaire : tout ce
> qu'il produit est une lecture du serveur ComfyUI et de la carte.

**La session qui livre ce lot a tourné sur le secondaire.** Relevé au début, avant d'écrire une
ligne :

```
GET http://127.0.0.1:8188/system_stats
  → WinError 10061 : l'ordinateur cible l'a expressément refusée
Get-CimInstance Win32_VideoController
  → Intel(R) Graphics — aucune RX 7900 XT, aucun ROCm
```

Conséquence, dite maintenant plutôt qu'à la fin : **les critères 1, 4 et une moitié du 3 et du
6 ne sont pas tenus**, et aucune de ces trois lacunes ne se rattrape par du code. Elles se
rattrapent en dix minutes sur le principal, et le §8 dit exactement comment.

⚠ **Ce n'est pas la première fois** : `docs/mesures/socle-generatif-2026-08-29.md` porte déjà
« trois des quatre mesures que le plan demandait n'ont pas pu être faites », pour la même
cause. Le `README-COMFYUI-28-30` §nouveau fait de terrain l'avait anticipé. Le fait qu'un plan
prévienne d'un risque ne le supprime pas ; ce qui le supprime est de **lancer la session sur
la bonne machine**.

**Ce qui a été fait malgré tout, et ce n'est pas rien** : tout ce que le plan demande de
*construire* est construit, et le critère 8 exige précisément que ça se **teste sans serveur**
— « la sonde et le validateur se testent contre un `/object_info` factice ». C'est la partie du
plan qui était conçue pour tourner ici, et elle tourne.

---

## 2. Étape 0 — ce qui a pu être relevé, et ce qui ne l'a pas été

| Étape | Ce que le plan demande | Verdict |
|---|---|---|
| **0.1** | version, variante, dossiers de modèles, nœuds tiers **avec leur licence** | ❌ **non relevé** — serveur absent. La commande qui le relève est livrée et testée |
| **0.2** | tableau nœud par nœud : le nœud existe-t-il, le modèle nommé est-il dans sa liste | ❌ **non relevé sur le vrai serveur** ; ✅ le calcul est livré, testé contre un `/object_info` factice, et se lance en une commande |
| **0.3** | combien de temps une session perd sur des causes déjà connues | ⚠ **partiellement** — le décompte des causes est fait (§3) ; le **temps perdu** ne l'est pas, faute d'accès aux journaux des 2026-08-29 et 30, qui sont sur le principal |

### 2.1 Ce que `--sonde` répondra, et avec quelle preuve

L'outil ne devine pas : il déduit ce qui se déduit, avec sa preuve, et nomme le reste.

| Question de l'étape 0.1 | Ce qui y répond | Ce que ça ne dit PAS |
|---|---|---|
| version | `system.comfyui_version` | — |
| variante | `system.embedded_python` : `true` = portable/standalone | ⚠ `false` ne distingue **pas** Desktop d'un `git clone` dans un venv. La sonde affiche « installée (Desktop ou venv) » plutôt que de choisir |
| dossier d'installation | `system.argv[0]`, le `main.py` lancé | rien si le serveur tourne sur une autre machine — la sonde le dit au lieu d'inventer un chemin |
| dossiers de modèles | `models/` et `extra_model_paths.yaml` cherchés **sur le disque**, sous l'installation | rien si l'installation n'est pas lisible d'ici |
| nœuds tiers | `python_module` de chaque nœud, préfixe `custom_nodes.` | ⚠ **la licence ne se déduit de rien.** Elle se vérifie à la source primaire et s'écrit à la main dans la fiche — le dépôt a déjà cette jurisprudence (poids de LaMa, lot 16) |

⚠ **Pourquoi `python_module` plutôt que la liste des dossiers de `custom_nodes/`** : un dossier
présent n'est pas un nœud chargé. Un paquet tiers qui a échoué à l'import laisse son dossier et
n'expose rien. La seule réponse mécaniquement vraie à « quels nœuds tiers tournent ici » est
celle que le serveur donne.

### 2.2 La commande qui referme cette lacune, sur le principal

```powershell
python tools/comfy.py --sonde        # tout le §2.1, en une requête de lecture
python tools/comfy.py --valider      # les trois graphes du dépôt, nœud par nœud, modèle par modèle
```

---

## 3. Étape 0.3 — combien de pannes connues se voient AVANT le GPU

Le §10 de `docs/procedures/comfyui.md` (ex-§9) liste les symptômes rencontrés les 2026-08-29 et
30, plus ceux qu'a ajoutés ce lot. Le décompte, ligne par ligne :

| Symptôme du tableau | Vu avant le GPU ? | Par quoi |
|---|---|---|
| Images brûlées, `cfg 4` + LoRA Lightning | ✅ | `--valider`, contrôle 5 |
| ~64 s **par pas** (encodeur sur GPU, transformeur rogné) | ❌ | c'est un comportement du serveur, pas une propriété du fichier |
| `TextEncodeQwenImageEditPlus` ne finit jamais (encodeur sur CPU en édition) | ❌ | idem |
| `Invalid image file: C:\…` | ✅ | `--valider`, contrôle 3 (le nom n'est pas dans la liste de `LoadImage`) |
| `canal « references » refusé` | ✅ | `--valider`, contrôle 4 — **c'était déjà le cas avant ce lot** |
| Workflow au format écran | ✅ | `--valider`, contrôle 1 — le client le disait déjà, mais **trop tard** |
| Un modèle n'apparaît pas dans la liste | ✅ | `--valider`, contrôle 3 |
| 12 Go occupés après un run | ❌ | volontaire (`decharger_image: false`) |
| ComfyUI plante en fin de run (segfault de `/free`) | ❌ | défaut de ComfyUI |
| La 1re image est deux fois plus lente | ❌ | normal |
| Copie non marquée chez ComfyUI (`SaveImage`) | ❌ | c'est le `PLAN-30` |
| Nœud tiers absent | ✅ | `--valider`, contrôle 2 |
| Image étrange, cause inconnue | ⚠ après coup | `--journal` : les trois lignes du serveur sont archivées **à côté de l'image** |
| « je ne sais pas ce que le projet envoie » | ⚠ avant, mais ce n'est pas un refus | `--graphe` |
| Deux runs, deux images différentes | ⚠ après coup | `--diff` |

**Six symptômes sur quinze sont attrapés mécaniquement avant le GPU**, trois se diagnostiquent
après coup avec un outil qui n'existait pas, et six sont des comportements du serveur qui ne se
voient pas dans un fichier.

⚠ **Ce que ce tableau ne dit PAS, et c'est la moitié de la question du plan.** Il compte des
**causes**, pas des **minutes**. Le plan demandait « combien de temps une session perd-elle » ;
répondre exigeait les journaux des sessions des 2026-08-29 et 30, qui sont sur le principal.
Le seul chiffre de temps qu'on puisse citer honnêtement est celui déjà publié : un
`POST /interrupt` a coûté **22 minutes** de réinitialisation au run suivant (2026-08-30), et une
première génération charge 12,84 Go + 9,38 Go depuis le disque. Un refus qui tombe avant la
bascule VRAM économise au minimum ce chargement ; **de combien en moyenne, ce lot ne le sait
pas**.

⚠ **Et la ligne la plus coûteuse du tableau n'est attrapée par rien de ce lot** : le
transformeur rogné, facteur **9,6** sur le temps par pas. Elle ne se voit pas dans le graphe.
Ce que ce lot y ajoute est plus modeste et vaut quand même : elle est désormais **archivée**,
donc une image lente ou étrange peut être expliquée après coup au lieu d'être devinée.

---

## 4. Les cinq vérifications, et le cas réel de chacune

C'est le tableau que le critère 3 demande. Chaque ligne a son test, et le nom du test est le
cas.

| # | Vérification | Le cas mesuré où elle aurait servi | Le test |
|---|---|---|---|
| 1 | le fichier est au **format API**, pas au format écran | §10, ligne 6 : « Angelith dit que le workflow n'est pas exploitable ». Le client savait déjà le dire — **au moment de générer** | `test_un_export_au_format_ECRAN_est_refuse` |
| 2 | chaque `class_type` **existe** sur ce serveur | §7 : `UnetLoaderGGUF` n'existe que si `ComfyUI-GGUF` est installé. Sur une autre machine, le graphe du dépôt échoue au premier appel | `test_un_noeud_ABSENT_du_serveur_est_refuse_avant_le_gpu` |
| 3 | chaque valeur de liste déroulante est **dans la liste** | §10, ligne 7 : « Un modèle n'apparaît pas dans la liste ». Un graphe versionné stocke le **nom**, pas un identifiant | `test_un_modele_RENOMME_est_attrape_dans_la_liste_du_noeud` |
| 4 | les **canaux** que ce graphe déclare | §10, ligne 5 : « canal « references » refusé » — un seul des trois graphes porte `%reference_1%` | `test_les_canaux_declares_sont_ceux_du_graphe` |
| 5 | la cohérence **pas / guidage** avec la LoRA du graphe | §10, ligne 1 : images brûlées. ⚠ **La seule dont l'échec ne produit AUCUN message** : ComfyUI exécute, et l'image sort | `test_une_lora_LIGHTNING_avec_un_guidage_de_4_est_refusee` |

### 4.1 Deux choix qui méritent d'être défendus

**La vérification 3 ne lit pas une liste de champs écrite à la main.** Le plan nommait
`unet_name`, `clip_name`, `vae_name`, `lora_name`, `image`. Une telle liste aurait raté
`ModelPatchLoader.name` — le nœud du canal que le `PLAN-30` vise. La règle appliquée est celle
de ComfyUI lui-même : **tout champ dont `/object_info` donne une liste de choix est une liste
déroulante, et le serveur refuse toute autre valeur.** La liste `CHAMPS_FICHIER` ne décide plus
de ce qui est vérifié, seulement du mot employé dans le message — « modèle » plutôt que
« valeur ». Effet de bord voulu : un `sampler_name` ou un `scheduler` renommé entre deux
versions de ComfyUI est attrapé aussi.

**Un serveur éteint donne « NON FAIT », jamais « passé ».** C'est le garde-fou central du lot, et
il a son test : `test_sans_serveur_les_verifications_2_et_3_sont_NON_FAITES`. Un validateur qui
refuserait un nœud parce que ComfyUI est éteint refuserait les trois graphes du dépôt à chaque
`--check` hors ligne — exactement le faux avertissement que `core/config_schema.py` décrit en
tête : « pire que pas de vérification du tout ». Les vérifications 1, 4 et 5 marchent hors
ligne, et c'est ce qui rend ce lot livrable depuis le PC secondaire.

### 4.2 La VRAM : le chiffre que le plan demande, et la correction qu'il fallait y apporter

Le plan demande de refuser quand « la VRAM libre est inférieure au pic mesuré (**14 417 Mio**
relevé le 2026-08-29 sur le graphe Lightning) ».

⚠ **Appliqué à la lettre, ce contrôle aurait été un faux avertissement à chaque seconde
génération.** Après un run, ComfyUI garde **12 083 Mio** résidents (mesuré le même jour) : la
VRAM *libre* tombe alors à ~8 Go, bien sous le pic — alors que relancer le même graphe ne
recharge rien du tout, puisque les modèles sont déjà là.

La comparaison retenue est donc **libre + ce que PyTorch a déjà réservé** (`torch_vram_total`),
qui est ce qu'une génération peut réellement occuper. Deux tests le tiennent :
`test_la_vram_RESERVEE_par_pytorch_compte_au_credit` et
`test_une_vram_trop_courte_est_dite_avec_son_pic_et_sa_date`.

⚠ **Le pic est celui d'UNE pile**, daté, sur une carte de 20 464 Mio. Sur une autre carte il ne
veut rien dire, et le message le dit plutôt que de laisser croire à une exigence du modèle.

---

## 5. Le relevé des affirmations d'état — L28.4

**La méthode, pour qu'elle se refasse en dix secondes :**

```powershell
grep -rnE "n'a jamais|n'ont jamais|pas encore|non mesur|n'est pas mesur|ne sont pas mesur|à vérifier|reste à mesurer|jamais exécut|n'a pas été" illustration/*.py core/*.py
```

**50 correspondances dans 25 fichiers.** La très grande majorité ne sont **pas** des
affirmations d'état : ce sont des conditions d'exécution (« une entrée qui n'est pas encore
romanisée », « un projet dont la bible n'a pas encore été commencée ») ou des libellés de motif.
Elles ne vieillissent pas, donc elles n'ont pas à porter de date.

**Sept sont de vraies affirmations d'état — un fait sur le projet, qui peut devenir faux :**

| Fichier | L'affirmation | Datée ? | Verdict |
|---|---|---|---|
| `illustration/comfyui.py` l. 34 | « ce client **n'a jamais tourné** contre un vrai serveur ComfyUI » | ❌ | ⚠ **PÉRIMÉE depuis la 2.16.0** — fausse pendant **six versions**. Corrigée par ce lot |
| `core/version.py` l. 71 | « le moteur réel n'a jamais tourné » | ✅ | à jour — un bloc « ⚠ MISE À JOUR 2.16.0 » la **lève** explicitement, sans l'effacer |
| `core/illustrations.py` l. 9 | « … dossiers `build/*/*/media/` **au 2026-08-29** » | ✅ | à jour |
| `illustration/identite.py` l. 38 | « le mécanisme est livré, l'axe n'est pas mesuré » (recadrage) | ❌ | vraie, mais muette sur sa date → **datée par ce lot** |
| `illustration/scene.py` l. 36 | « l'apport de la clause de scène n'est pas mesuré » | ❌ | vraie → **datée** |
| `illustration/selection.py` l. 81 | « le coût de la seconde ancre n'est pas mesuré » | ❌ | vraie → **datée** |
| `core/illustrations.py` l. 722 | « cet écart n'a pas encore d'échelle » | ❌ | vraie → **datée** |

**Une périmée sur sept, et elle l'était depuis six versions.** C'est le chiffre qui justifie la
règle, écrite au §5 bis de `docs/plans/00-CONTEXTE-AGENT.md` :

> Toute affirmation d'ÉTAT dans le code porte SA DATE et le document qui l'établit. Un
> commentaire qui vieillit sans le dire est un faux avertissement, et un faux avertissement
> cesse d'être lu.

⚠ **La correction retenue pour `comfyui.py` n'efface pas la phrase fausse, elle l'historise.**
Le paragraphe dit maintenant ce qui a été affirmé, jusqu'à quand, et par quoi c'est remplacé —
avec un tableau à trois lignes dont la troisième est « `stable-diffusion.cpp` et `diffusers` :
**jamais** ». Effacer aurait fait disparaître la leçon avec l'erreur.

⚠ **Cette règle n'est pas testée mécaniquement, et c'est délibéré.** Même raison que pour la
règle des chiffres, écrite dans `tests/test_coherence_chiffres.py` : « ce n'est pas décidable
par une expression régulière ; un garde-fou qui produit des faux positifs sur de la prose est
contourné avant d'avoir servi ». Elle tient à la relecture, et la commande ci-dessus la refait.

---

## 6. Les neuf critères du plan, un par un

| # | Critère | Verdict |
|---|---|---|
| 1 | variante, dossiers de modèles et nœuds tiers **relevés et écrits**, avec `/system_stats` cité | ❌ **NON TENU** — PC secondaire. L'outil qui le relève est livré ; `docs/procedures/comfyui.md` §0 bis dit que le §0 n'a pas été remesuré, et porte la commande |
| 2 | `--sonde` et `--valider` existent, **réutilisent** le sondage de `tools/banc_prompt.py` (extrait, pas dupliqué), et **ne peuvent pas générer** | ✅ **TENU**. Le sondage vit dans `illustration/sonde.py` ; `banc_prompt.canaux` et `_vram_residente` l'appellent, et n'ouvrent plus une seule URL. « Ne peut pas générer » est **compté**, pas relu : `test_aucune_sous_commande_n_envoie_de_generation` vérifie zéro `POST` |
| 3 | `--valider` attrape les cinq cas sur les trois graphes du dépôt ; tableau publié avec un cas réel par vérification | ⚠ **TENU à moitié**. Le tableau est au §4, les cinq tests passent, et les trois graphes du dépôt sont validés par un test. Mais les vérifications 2 et 3 n'ont été exercées **que contre un `/object_info` factice** : jamais contre le vrai serveur |
| 4 | `--graphe` produit un `.api.json` qui **se recharge dans ComfyUI** et reproduit l'image à la main, vérifié une fois, image comparée | ❌ **NON TENU** — aucun ComfyUI ici. Ce qui est tenu : le fichier est produit, il est au format API, et le nom que chaque référence portera est **identique** à celui du chemin nominal (`test_le_nom_televerse_est_le_MEME_avec_ou_sans_serveur`) — c'est ce qui rend la reproduction possible, pas ce qui la prouve |
| 5 | `--check` refuse **avant tout déchargement de LLM**, chaque refus porte sa correction | ✅ **TENU, et élargi**. ⚠ Tenu trivialement pour `--check`, qui ne décharge jamais rien : le critère, lu à la lettre, ne prouvait pas grand-chose. Le lot va donc plus loin que le plan et met la **même** validation dans `phase_image`, juste avant la bascule VRAM (`_valider_le_graphe`). Trois tests |
| 6 | le graphe envoyé et les trois lignes de journal **archivés à côté de chaque image** | ⚠ **TENU en code, non vérifié sur un vrai run.** `<image>.png.graphe.json` + `journal_serveur` dans le sidecar, six tests dont un de bout en bout par le client. Mais **aucune image n'a été générée** dans cette session, et la route `/internal/logs/raw` n'a jamais été appelée contre un vrai ComfyUI — seulement contre un doublon |
| 7 | relevé des affirmations d'état publié ; `comfyui.py` l. 34 corrigée ; la règle écrite dans `00-CONTEXTE-AGENT.md` | ✅ **TENU** — §5 ci-dessus |
| 8 | `ruff check .` passe ; `pytest -q -m "not modeles and not lent"` passe **sans serveur ComfyUI** | ✅ **TENU** — §7 |
| 9 | ce document reprend les critères un par un, y compris les non tenus, et dit ce que la mesure ne dit pas | ✅ ce document |

**Trois critères sur neuf ne sont pas tenus, et les trois ont la même cause.** Aucun ne
demande du code : ils demandent une session sur le PC principal.

---

## 7. Ce qui a changé, chiffré

| | avant (`f15792a`, 2.21.0) | après (2.22.0) |
|---|---:|---:|
| tests collectés, toutes dépendances optionnelles | 3 811 | **3 872** |
| boucle courte (`-m "not lent and not modeles"`) | 3 754 | **3 815** |
| désélectionnés (`lent`, `modeles`) | 57 | 57 |
| `ruff check .` | ✓ | ✓ |

**+61 tests**, tous hors marqueur, donc tous exécutés en CI. Répartition :
`test_illustration_sonde.py` (15), `test_illustration_validation.py` (26 — dont 3 sur le refus
avant la bascule VRAM), `test_tools_comfy.py` (15), et 6 dans `test_illustration_marquage.py`
pour la trace L28.3. Aucun test n'a été retiré ni renommé : le diff des identifiants collectés
est de **61 ajouts, 0 suppression**.

**Modules neufs** : `illustration/sonde.py`, `illustration/validation.py`, `tools/comfy.py`.
Aucune dépendance ajoutée — `urllib` et `difflib`, comme le reste de la brique.

**`config.yaml` n'a pas changé.** Aucune clé n'a été ajoutée par ce lot : la sonde et le
validateur lisent `illustration.comfyui.base_url`, `.workflow` et `illustration.image.pas` /
`.guidage`, qui existaient tous. C'est l'iso-comportement du §9.3 du contexte agent, dans sa
forme la plus simple : il n'y a rien à désarmer.

**Le seul changement de comportement du chemin nominal** est un **refus de plus** avant la
bascule VRAM, sur un graphe que ComfyUI aurait de toute façon rejeté (contrôles 2 et 3) ou qui
aurait produit une image brûlée sans le dire (contrôle 5). Un utilisateur dont la configuration
est cohérente ne voit aucune différence — c'est le cas du `config.yaml` livré, vérifié :
`pas: 4`, `guidage: 1.0`, graphe Lightning, **aucun constat**.

---

## 8. Ce que la mesure ne dit pas

1. **Rien n'a été vérifié contre un vrai serveur ComfyUI.** Tout ce qui touche à
   `/object_info`, `/system_stats` et `/internal/logs/raw` est vérifié contre des doublons
   écrits à la main, à partir des formes documentées et de ce que
   `docs/mesures/connecteur-qwen-2026-08-29.md` a relevé. **Si ComfyUI 0.34.2 rend une de ces
   trois routes sous une autre forme, ce lot s'en apercevra à la première exécution réelle**, pas
   avant. Les trois lectures dégradent proprement — un relevé injoignable, un journal
   indisponible — mais « dégrade proprement » n'est pas « a été vu marcher ».
2. **`/internal/logs/raw` n'est pas garantie.** Elle existe sur les versions récentes de
   ComfyUI ; elle n'est ni versionnée ni documentée comme une API stable. Si elle manque, le
   sidecar porte `journal_serveur: {disponible: false, motif: …}` et le run continue — c'est
   voulu, une trace qui manque ne doit pas faire échouer un run dont l'image est écrite.
3. **La corrélation des lignes de journal est une fenêtre, pas un `prompt_id`.** ComfyUI
   n'étiquette pas ses lignes par requête. Sur un serveur qui ne sert que ce run — le cas
   nominal — la queue du journal est la bonne fenêtre ; sur un serveur partagé, ce sont les
   dernières lignes, et le champ `correlation` du sidecar le dit en toutes lettres.
4. **Le pic de VRAM reste non observable pendant le calcul.** Ce client parle à ComfyUI par
   HTTP et n'a aucune vue sur l'allocateur : `vram_pic_octets` reste `None` sur ce moteur, et le
   14 417 Mio du seuil est un chiffre **importé** d'une mesure passée, pas relevé à l'exécution.
5. **Aucune image n'a été produite, donc rien n'est dit sur les images.** Le lot n'en change
   aucune — c'est sa nature attendue — mais l'absence de changement n'a pas été **constatée** par
   un run avant/après. Elle est argumentée : les seuls chemins touchés dans la génération sont
   l'ajout de deux clés à `Sortie.provenance` et l'écriture d'un fichier `.json` de plus.
6. **Le temps épargné n'est pas mesuré** (§3), seulement le nombre de causes attrapées.

## 9. Ce qu'il reste à faire, sur le PC principal

Dix minutes, dans cet ordre :

```powershell
python tools/comfy.py --sonde                     # critère 1 : colle la sortie dans procedures/comfyui.md §0
python tools/comfy.py --valider                   # critère 3 : les trois graphes contre le VRAI /object_info
python run_illustration.py --check                # critère 5 : la validation dans le diagnostic
python tools/comfy.py --graphe build/<Projet>/illustrations/requete.yaml
#   … glisse le .api.json produit dans ComfyUI, lance, compare l'image au PNG du run — critère 4
python run_illustration.py "<Projet>" --phase image   # critère 6 : vérifie le .graphe.json et les 3 lignes
python tools/comfy.py --journal                   # … et qu'elles se relisent
```

Chacune de ces six lignes ferme une case du §6. Aucune ne demande d'écrire du code.

---

## 10. Addendum du 2026-09-03 — la session sur le PC PRINCIPAL

> **Ce que cet addendum ajoute, et ce qu'il ne touche pas.** Le document ci-dessus décrit l'état
> du 2026-09-02, depuis le PC secondaire ; il n'est **pas** réécrit — `00-CONTEXTE-AGENT.md`
> §5 bis. Cette section publie les relevés du **bloc A** de
> `docs/plans/A-EXECUTER-SUR-LE-PC-PRINCIPAL-28-30.md`, faits le **2026-09-03** sur la machine
> qui a la carte, et rien d'autre.
>
> **Version du dépôt** : `2.24.0`, commit `1618ad1`, arbre propre au départ — **aucune ligne de
> code n'a été écrite par cette session**, c'est la consigne du plan.

### 10.1 Comment le serveur a été lancé, et pourquoi ça se dit

ComfyUI n'était pas en marche. Il a été démarré **à la main**, depuis l'environnement que
Comfy Desktop gère, avec **les arguments que Desktop utilise lui-même** (relevés dans son
`installations.json`) :

```
…\ComfyUI-Installs\ComfyUI\ComfyUI\.venv\Scripts\python.exe
  …\ComfyUI-Installs\ComfyUI\ComfyUI\main.py
  --port 8188 --enable-manager
  --extra-model-paths-config "%APPDATA%\Comfy Desktop\instance-model-paths\inst-1788013776283.yaml"
```

⚠ **Deux choses se sont apprises rien qu'en le lançant, et elles valent d'être écrites.**

1. **L'environnement Python de ComfyUI n'est pas celui qu'on croit.** Le premier essai est parti
   de `standalone-env\python.exe`, le seul interpréteur visible à la racine de l'installation :
   `ModuleNotFoundError: No module named 'torch'`. Le vrai environnement est un
   **`.venv` imbriqué**, `…\ComfyUI-Installs\ComfyUI\ComfyUI\.venv\`, et c'est **lui** qui porte
   `torch 2.12.0+rocm7.14.0`. Quelqu'un qui veut relancer ce serveur hors de Desktop doit le
   savoir ; rien dans `docs/procedures/comfyui.md` ne le disait.
2. **`--enable-manager` ne change rien au relevé.** La sonde a été lancée deux fois, avec et
   sans : **907 nœuds exposés** dans les deux cas, **même** liste de nœuds tiers. Le
   gestionnaire n'expose aucun nœud, donc le chiffre de 907 est comparable à celui du
   2026-08-29 quel que soit le mode de lancement. C'est une **non**-différence, et elle est
   utile : elle ferme une question qu'on se serait posée à chaque relevé futur.

### 10.2 Critère 1 — ce que le serveur expose réellement ✅ **TENU**

`python tools/comfy.py --sonde`, code de sortie **0**. Le relevé est recopié dans
`docs/procedures/comfyui.md` **§0**, daté du jour, et l'avertissement « ce tableau n'a pas été
remesuré » y est **levé** par un bloc daté plutôt qu'effacé.

**Ce qui est confirmé, à l'identique du 2026-08-29** : ComfyUI 0.34.2, `torch 2.12.0+rocm7.14.0`,
Python 3.13.12, **907 nœuds**, RX 7900 XT à `21 458 059 264` octets de VRAM. Cinq chiffres sur
cinq tiennent après cinq jours — ce n'est pas rien pour une pile ROCm.

**Ce qui est tranché, et qui ne l'était pas** : la variante. Le §0 opposait « standalone
`win-amd` » (le document de mesure) à « ComfyUI Desktop » (la réponse d'Alexandre) et demandait
de choisir. **La réponse est : les deux.** `Comfy Desktop 1.0.46` pilote un environnement
standalone `win-amd` (bundle `v0.29.0-env1`). La question ne se tranchait pas parce qu'elle
était mal posée.

**La licence des nœuds, vérifiée à la source primaire le 2026-09-03** — elle ne se déduit de
rien, c'est la règle :

| Nœud | Module | Licence | Vérifiée où |
|---|---|---|---|
| `ComfyUI-GGUF` (6 nœuds) | `custom_nodes/ComfyUI-GGUF`, commit `6ea2651` du 2026-01-12 | **Apache-2.0** | `github.com/city96/ComfyUI-GGUF` **et** le fichier `LICENSE` de la copie installée, le 2026-09-03 |
| `websocket_image_save` (1 nœud) | `custom_nodes/websocket_image_save.py` | **GPL-3.0** — celle de ComfyUI | ⚠ **ce n'est pas un nœud tiers** : `git ls-files` sur la v0.34.2 le rend, il est versionné par ComfyUI lui-même. La sonde le compte comme tiers parce qu'il vit sous `custom_nodes/` |

### 10.3 ⚠ Trois écarts entre ce que la sonde affirme et ce que la machine est

**C'est le résultat le plus utile de la session, et c'est un résultat négatif.** La sonde du lot
28 a été écrite et testée contre un `/object_info` et un `/system_stats` factices ; lancée pour
la première fois contre le vrai serveur, elle **répond faux sur trois lignes**, toutes les trois
sur des questions que le §0 de la fiche lui déléguait.

| Ligne affichée | Ce qui est vrai | Cause |
|---|---|---|
| `Modèles : …\ComfyUI\models` | les modèles sont sous `…\Comfy-Desktop\ComfyUI-Shared\models` | `sonde.dossiers_de_modeles()` déduit `models/` du dossier de `main.py`. Sous Desktop ce dossier existe, mais **ne contient que ses `put_*_files_here`** |
| `extra_model_paths.yaml : absent — les modèles sont lus sous l'installation` | un fichier de chemins **existe**, hors de l'installation | la sonde ne le cherche qu'à `<installation>/extra_model_paths.yaml`. Desktop le passe en argument |
| `installée (Desktop ou venv)` | Desktop, sans ambiguïté | `/system_stats` rend `deploy_environment: "local-desktop2-standalone"` ; la sonde ne lit que `embedded_python` |

⚠ **Les deux premières se tiennent, et c'est ce qui les rend nuisibles.** La sonde conclut « les
modèles sont lus sous l'installation » **parce qu'**elle n'a pas trouvé le fichier de chemins.
Un lecteur qui la croit dépose le poids du lot 30 dans un dossier que ce serveur ne lit pas —
exactement le piège que le §2 de `docs/procedures/comfyui.md` existe pour éviter.

⚠ **Le §2.1 du présent document promettait le contraire**, et il faut le dire : « l'outil ne
devine pas : il déduit ce qui se déduit, avec sa preuve, et nomme le reste ». Sur ces trois
lignes il **devine**, et il ne le dit pas. Le §8.1 avait prévu le mécanisme — « ce lot s'en
apercevra à la première exécution réelle » — sans prévoir que ce serait sur `/system_stats`
plutôt que sur `/object_info`.

⚠ **La correction n'a pas été écrite, et c'est volontaire** : le plan interdit à cette session
d'écrire du code. La matière est là — `/system_stats` rend déjà `argv`, où
`--extra-model-paths-config` figure en toutes lettres, et `deploy_environment`. Les trois lignes
se corrigent par de la **lecture de champs existants**, pas par une requête de plus.

### 10.4 Critère 3 — les quatre graphes contre le VRAI `/object_info` ✅ **TENU**

`python tools/comfy.py --valider`, code de sortie **0**, conforme à ce que le plan attendait :

| Graphe | Attendu par le plan | Relevé |
|---|---|---|
| `qwen-image-2512.api.json` | ✓ + réserve `copie_non_marquee` | ✓ — 10 nœuds exposés, **7** valeurs vérifiées dans les listes |
| `qwen-image-2512-lightning.api.json` | idem | ✓ — 11 nœuds, **8** valeurs |
| `qwen-image-edit-2511.api.json` | idem | ✓ — 14 nœuds, **8** valeurs |
| `qwen-image-edit-2511-controle.api.json` | ⚑ CANDIDAT puis des **réserves** | ⚑ CANDIDAT, puis `modele_absent` + `canal_exige` + `copie_non_marquee` — **aucun refus** |

**Les vérifications 2 et 3 ont été exercées pour la première fois**, et elles font ce qu'elles
promettaient : les **52 nœuds** des quatre graphes existent tous sur ce serveur, et les listes de
fichiers sont vérifiées valeur par valeur. La seule valeur introuvable est la vraie :
`qwen_image_canny_diffsynth_controlnet.safetensors`, que `ModelPatchLoader` n'expose pas — son
dossier `model_patches/` est **vide**, ce qui est exact.

⚠ **Point de vérification du lot 30 : la rétrogradation `_retrograder` fonctionne.** Le graphe
candidat produit des réserves et **ne fait pas échouer la commande** — code 0. C'était la
question posée ; la réponse est oui.

⚠ **Une prémisse du PLAN est fausse — et le lot 30, lui, avait raison.** Le plan attendait des
réserves « sur le nœud **et** le poids absents ». Sur cette machine, **le nœud n'est pas
absent** : `ModelPatchLoader` est exposé par ComfyUI 0.34.2 lui-même — il fait partie des 17
nœuds validés du graphe candidat. Seul le **poids** manque. C'est exactement ce que
`docs/mesures/canaux-2026-09-03.md` §3.2 avait écrit — « nœud : **intégré à ComfyUI** » — et
c'est le plan qui a durci la prévision en écrivant le contraire. **Le relevé confirme le
document de mesure contre le plan**, ce qui est le bon sens de lecture.

### 10.5 Critère 5 — le diagnostic avec un vrai serveur ✅ **TENU**, et une réserve qui compte

`python run_illustration.py --check` — **et ce n'est pas ce que le plan attendait.** Avec la
configuration **livrée par défaut**, la sortie ne contient **aucune** validation de graphe :

```
Moteur : factice  — aucun poids, aucun GPU ; il sert à vérifier la chaîne, pas à illustrer
```

`run_illustration.py` l. 336 ne lance `_diagnostic_comfy` que si `illustration.moteur ==
"comfyui"`, et le défaut livré est `"factice"` (`config.yaml` l. 1995). **Le plan a supposé une
configuration qui n'est pas celle du dépôt** — et le §9 du présent document aussi, quand il
écrivait « lance `--check` sur le principal, dix minutes ».

Relancé avec la seule clé qui change (`moteur: "comfyui"`, sur une **copie** de `config.yaml` ;
le fichier du dépôt n'a pas été touché), le critère est tenu :

```
  Validation du graphe (avant le GPU, PLAN-28 L28.2) :
    format API : ✓ le fichier est un graphe au format API
    nœuds exposés : ✓ les 11 nœuds du graphe existent sur http://127.0.0.1:8188
    fichiers et listes : ✓ 8 valeur(s) vérifiée(s) dans les listes du serveur
    canaux déclarés : ✓ prompt, prompt_negatif
    pas / guidage : ✓ compatible avec Qwen-Image-2512-Lightning-4steps-V1.0-bf16.safetensors
    sortie du graphe : ⚠ SaveImage — copie non marquée dans output/
```

**C'est le point que le §6 appelait « tenu trivialement ».** Les deux vérifications s'affichent
**passées** au lieu de « NON FAIT », ce qu'aucune session n'avait vu. Le critère est tenu — à la
condition, désormais écrite, que le moteur soit celui qui parle à ComfyUI.

### 10.6 Critères 4 et 6 — non faits, et pourquoi

| # | Critère | Verdict au 2026-09-03 |
|---|---|---|
| 4 | le `.api.json` se recharge dans ComfyUI et reproduit l'image à la main | ❌ **non fait** — c'est le bloc **D.1** du plan : il demande une génération et un geste à la souris. Le bloc A s'arrête avant |
| 6 | le graphe et les trois lignes de journal archivés à côté de chaque image | ❌ **non fait** — bloc **D.2**, même raison. `/internal/logs/raw` n'a **toujours** jamais été appelée contre un vrai ComfyUI |

### 10.7 Les neuf critères, réévalués au 2026-09-03

| # | Verdict au 2026-09-02 | Verdict au 2026-09-03 |
|---|---|---|
| 1 | ❌ non tenu | ✅ **TENU** — §10.2, `docs/procedures/comfyui.md` §0 daté du jour |
| 2 | ✅ tenu | ✅ tenu (inchangé) |
| 3 | ⚠ à moitié | ✅ **TENU** — §10.4, vérifications 2 et 3 exercées contre le vrai `/object_info` |
| 4 | ❌ non tenu | ❌ non tenu — bloc D.1 |
| 5 | ✅ tenu « trivialement » | ✅ **TENU réellement** — §10.5, sous réserve de `moteur: "comfyui"` |
| 6 | ⚠ tenu en code | ⚠ inchangé — bloc D.2 |
| 7 | ✅ tenu | ✅ tenu (inchangé) |
| 8 | ✅ tenu | ✅ tenu (inchangé) |
| 9 | ✅ | ✅ ce document, addendum compris |

**Deux critères passent de « non tenu » ou « à moitié » à « tenu ». Deux restent ouverts, et les
deux attendent une génération**, pas une machine : la machine, elle, est là.

⚠ **Trois cases se ferment, un défaut s'ouvre.** Le §10.3 n'entre dans aucun des neuf critères —
aucun ne demandait « la sonde dit-elle vrai ». C'est la limite de la grille, pas de la mesure.

### 10.8 Ce que cet addendum ne dit pas

1. **Rien n'a été généré.** Le bloc A l'exclut. Tout ce qui touche à `/prompt`, à
   `/internal/logs/raw`, au `.graphe.json` et aux trois lignes de journal reste dans l'état du
   §8 : vérifié contre des doublons, jamais vu marcher.
2. **La sonde a été lancée sur un serveur au repos**, jamais pendant un calcul. Les 20 317 Mio
   libres sont ceux d'un serveur qui n'a rien chargé ; ils ne disent rien de la marge en cours de
   génération.
3. **Les trois écarts du §10.3 n'ont pas été corrigés, donc pas non plus testés.** Ce qui est
   publié est le constat, avec les champs qui permettraient la correction. Personne n'a vérifié
   que lire `argv` suffit dans tous les cas — un chemin relatif, par exemple.
4. **Un seul poste de travail.** Tout ce qui précède décrit une installation Desktop sur Windows
   avec ROCm. Une installation portable sous Linux répondrait autrement, et la sonde y répondrait
   peut-être juste.
5. **Le serveur a été lancé par cette session, pas par Desktop.** Les arguments sont ceux de
   Desktop, mais la fenêtre de l'application n'était pas ouverte. Rien n'indique que ça change
   quoi que ce soit à `/object_info` ni à `/system_stats` — et rien ne le prouve non plus.
