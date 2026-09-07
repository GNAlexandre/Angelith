# L'atelier dans l'interface, et ce qui sort du dossier — lot 27, 2026-09-02

> **Le document du `PLAN-27`.** Il reprend **les treize critères numérotés du §3 du plan un
> par un**, y compris les non tenus, plus **trois exigences** que L27.1, L27.4 et L27.5 posent
> sans les numéroter. Il publie le calcul de poids disque et dit **ce que la mesure ne dit
> pas**.
>
> Le plan demandait `docs/atelier-illustration-<date>.md` ; le fichier vit sous
> `docs/mesures/` parce que c'est la convention du dépôt (`00-CONTEXTE-AGENT.md` §9.6 :
> « un document **`docs/mesures/<sujet>-<date>.md>`** »). Deux emplacements pour la même
> famille de documents auraient été le vrai défaut.

| | |
|---|---|
| Date | **2026-09-02** |
| Version livrée | **2.21.0** |
| Commit de départ | `6779edc` (2.20.0) |
| Empreinte SHA-256 de `config.yaml` **livré par ce lot** | `ae2de92caa123b44dab956a682e3975db5c16836c53f35f10a08fab415b834a7` |
| Machine | Windows 11, Python 3.12, Pandoc 3.10, WeasyPrint présent |
| GPU | **aucun run GPU dans cette session** — voir §7, « ce que la mesure ne dit pas » |

---

## 1. Étape 0.1 — le chiffre, et l'interface qu'il impose

Le plan interdit de dessiner avant d'avoir le chiffre. **Il n'a pas eu besoin d'être remesuré :
les lots 24 à 26 l'ont publié trois fois, sur la même carte, avec leurs dénominateurs.** Le
refaire aurait produit un quatrième nombre à confronter aux trois autres, ce que
`docs/chiffres-de-reference.md` désigne précisément comme le défaut à éviter.

Les trois relevés sont recopiés dans `illustration/attente.py:MESURES`, **avec** leur date,
leur échantillon, leur machine et leur source :

| Date | s / image | n | Moteur | Source |
|---|---:|---:|---|---|
| 2026-08-29 | **103,7** (médiane) | 4 | ComfyUI 0.34.2 · Qwen-Image-2512 GGUF Q4_1 | `connecteur-qwen-2026-08-29.md` |
| 2026-08-31 | 857,7 | 1 | ComfyUI · Qwen-Image-Edit-2511 GGUF Q4_1 | `atelier-2026-08-31.md` §3.4 |
| 2026-08-29 | 1 524,0 (pire cas) | 1 | ComfyUI 0.34.2 · Qwen-Image-2512 GGUF Q4_1 | `identite-2026-08-29.md` |

**Médiane pondérée par l'échantillon : 103,7 s.** Le tableau de l'étape 0.1 donne trois
tranches — < 10 s, 10 à 60 s, > 60 s. 103,7 s est **1,7× le seuil du haut**, et le pire cas
**25×**. Aucun relevé ne tombe dans une autre tranche.

> **Tranche imposée : « run par lot — on lance, on revient ».**

Ce que l'interface en fait, et ce sont quatre décisions et non quatre préférences :

1. elle **annonce la fourchette mesurée avant** d'engager le GPU (`attente.annonce`), comme
   `gui/lanceur.py:_confirmer` le fait déjà pour un run ;
2. sa barre reste **indéterminée** tant qu'aucune image n'est terminée. Le rapport entre le
   meilleur et le pire relevé est de **14,7** : une barre qui annoncerait « 42 % » après 43 s
   se tromperait d'un facteur dix un jour sur deux. Le dépôt a déjà payé cette leçon —
   `SECONDES_PAR_RELETTRAGE` valait 1,5 s pour un coût réel de 4,0 s, « trois fois trop bas ne
   la rend pas approximative, ça la rend trompeuse » ;
3. elle compte en **images terminées**, jamais en pas de débruitage ;
4. le travail passe par le fil de travail : **la fenêtre reste utilisable**.

### Une prémisse du plan est fausse, et c'est un résultat

L27.2 écrit que « le chiffre mesuré peut faire de la bascule le poste le plus long ».
**Il ne le fait pas sur cette machine** : la bascule VRAM coûte **2,03 s** par run (mesuré le
2026-08-29, trois essais, `_basculer_vram`), soit **2 % du coût d'UNE image**. Elle n'est pas
le poste dominant, et elle ne le sera pas tant qu'une image coûtera plus de cent secondes.

La progression la distingue quand même — `préparation (LLM)` / `bascule de modèle` /
`génération (image)` —, et pas par symétrie : une barre immobile pendant deux secondes doit
dire que ce n'est pas la génération qui a commencé. Un test (`test_illustration_attente.py`)
échouera le jour où l'un des deux chiffres bougera assez pour renverser ce rapport.

## 2. Étape 0.2 — où vont les fichiers, et pourquoi ce n'est pas `build/` partout

Tranché comme le plan le recommandait :

```
build/<Projet>/illustrations/              candidates   — régénérable par contrat
build/<Projet>/illustrations/rejetees/     jetées       — conservées, jamais supprimées
sources/<Projet>/illustrations/            RETENUES     — survit à `rm -r build/`
```

`.gitignore` écrit que `build/` porte des « sorties de traduction (régénérables :
`python run.py` / `run_manga.py`) ». Une image produite en 103,7 s de GPU et retenue par un
humain **n'est pas régénérable**, et ce n'est pas une opinion : `orchestrateur.rejouer`
mesurait déjà que « la plupart des backends de diffusion ne sont pas déterministes d'une
exécution à l'autre ». Un `rm -r build/` — que le dépôt **recommande lui-même** après un
MAJEUR — détruirait donc le travail de sélection.

⚠ **Conséquence : la brique a une SECONDE racine d'écriture**, la première depuis le lot 24.
C'est un sous-dossier **neuf** de `sources/<Projet>/`, jamais le dossier du projet lui-même :
`frontiere.perimetre` ne laisse toujours pas approcher `bible.yaml`, `glossaire.yaml` ni un
fichier de l'œuvre. Le geste « je garde » déplace le fichier, ce qui donne aussi un sens fort
à « garder ».

## 3. Le poids sur le disque, calculé et publié (L27.5)

Le plan demande de publier le calcul. Il vit dans `illustration/galerie.py:calcul_du_poids`,
pour que `--check` et ce document lisent le **même** :

```
119 personnages × 8 images = 952 PNG
2,1 Mo par PNG   (médiane mesurée sur les 11 images 1328×1328 du run du 2026-08-29 ;
                  de 1,4 à 3,1 Mo)   + 5 ko de sidecar de provenance
→ 2,0 Go pour l'œuvre entière ;  3,0 Go si toutes les images tombent au pire cas mesuré
```

119 personnages est le chiffre **réel** de `manga D`, relevé le 2026-08-27 avec les
171 personnages des cinq projets à glossaire vivant. Ce n'est donc pas une hypothèse.

⚠ **Et les images retenues ne se libèrent pas toutes seules** : elles vivent sous `sources/`,
donc un `rm -r build/` ne les touche pas. C'est voulu — c'est ce qui les protège — et c'est
aussi pourquoi la commande d'inventaire et la purge existent.

## 4. Les treize critères numérotés, plus trois exigences — un par un

| # | Critère | Verdict |
|---|---|---|
| 1 | Le chiffre de l'étape 0.1 est publié et l'interface correspond à la tranche | **tenu** — §1, et `test_le_depot_est_dans_la_tranche_run_par_lot` |
| 1 bis | L'écran montre prompt, prompt négatif, vignettes **avec motif**, source des attributs ; un test interdit d'atteindre la phase 2 sans lui | **tenu** — `test_illustration_relecture.py`, 26 tests, dont un test `ast` sur `gui/atelier.py` |
| 1 ter | La progression distingue préparation / bascule / génération, avec le temps réel | **tenu** — `illustration/progression.py`, 10 tests, horloge injectée |
| 2 | Personnage sans référence validée : grisé, infobulle, aucun message d'erreur après le clic | **tenu** — `test_un_personnage_sans_reference_est_grise_et_non_cliquable` |
| 3 | Toute la logique dans `illustration/`, testable sans PySide6 ; comptes publiés | **tenu** — §5 |
| 4 | L'annulation décharge la VRAM et recharge le LLM, testé y compris sur erreur | **tenu avec une réserve nommée** — §6 |
| 5 | Une image générée **ne peut pas** devenir une référence. Test dédié | **tenu** — trois mécanismes, aller-retour complet testé |
| 6 | Un rejet ne supprime rien | **tenu** — `test_jeter_deplace_et_ne_supprime_RIEN` |
| 7 | `inserer_dans_sorties: false` par défaut ; tome iso-octet ; empreinte annoncée | **tenu** — empreinte en tête de ce document |
| 8 | La légende est dans les trois formats, non désactivable ; contrat `reference.docx` intact | **tenu** — vérifié avec le vrai Pandoc 3.10 : DOCX, EPUB, PDF |
| 9 | Le test de collision de noms avec la renumérotation des médias existe | **tenu** — `test_une_illustration_ne_peut_pas_collisionner_avec_un_media` |
| 10 | `ruff check .` passe ; `pytest -q -m "not modeles and not lent"` passe sans poids ni GPU | **tenu** |
| 11 | Ce document | **tenu** |
| L27.1 pt 5 | Bouton « Ouvrir la bible » | **tenu** — et il dit la commande à taper quand la bible n'existe pas encore |
| L27.4 pt 3 | `RAPPORT.md` liste les images insérées, avec personnage et graine | **tenu** — `insertion.lignes_de_rapport` |
| L27.5 | Une commande **et** un bouton : poids, comptes, purge avec confirmation | **tenu** — `--inventaire` / `--purger`, et les deux boutons de l'onglet |

### Les points du plan volontairement NON faits, et pourquoi

- **Aucune fonction de partage, d'export public, de mise en ligne ou de génération de planche
  publiable.** L'usage arrêté est privé (README de série §1) ; le lot n'en facilite aucune.
- **Aucune retouche d'image dans l'interface** (recadrage, correction). C'est un lot séparé,
  et il rouvrirait le §4 du README de série.
- **Aucun changement au pipeline de traduction** — aucun prompt, aucun seuil, aucune étape,
  aucun format de sortie — **sauf** la clé d'insertion, désarmée, et le point d'appel qui la
  lit.
- **Aucun éditeur de masque.** L'écran sait **désarmer** un canal structuré, pas l'éditer :
  « un éditeur de masque est un lot à lui seul, et il n'est pas celui-ci ».

## 5. Critère 3 — les comptes de tests, avec et sans Qt

| | avec PySide6 | sans PySide6 | écart |
|---|---:|---:|---:|
| avant le lot (2026-09-02, `6779edc`) | 3 682 | 3 480 | 202 |
| après le lot | **3 811** | **3 592** | **219** |
| **tests neufs** | **129** | **112** | **17** |

**86,8 % des tests neufs tournent sans PySide6.** C'est ce que le critère demandait :
« si votre lot ajoute 40 tests dont 35 exigent Qt, la règle a été violée ». Ici c'est
l'inverse — les dix-sept tests Qt vérifient **seulement** ce qui est réellement du Qt :
l'onglet existe, la fenêtre se construit sans la brique, un item de liste est grisé avec son
infobulle, l'annonce de coût s'affiche, et rien ne se persiste qui ne doive l'être.

⚠ **Le dénominateur du `00-CONTEXTE-AGENT.md` était périmé de trois lots.** Il annonçait
« 2 007 collectés avec, 1 879 sans », mesuré le 2026-08-26, et plusieurs plans l'ont recopié
depuis. Le vrai écart au 2026-09-02, **avant** ce lot, était 3 682 / 3 480. Le contexte agent
et `docs/chiffres-de-reference.md` sont mis à jour par ce lot, avec leur date.

⚠ **Et ce couple ne s'unifie pas à celui de `ci.yml`** (2 644 / 2 504, soit 140, au
2026-08-27) : la CI mesure une **autre configuration** — socle + GUI + dev, **sans**
`requirements-manga.txt`. Le remesurer demanderait un run de CI dédié ; il garde donc sa date,
comme la règle des chiffres l'exige.

Le « sans PySide6 » est mesuré en rendant `PySide6` introuvable par un `meta_path` bloquant
pendant la collecte, pas en désinstallant le paquet. Ce que cette méthode **ne** reproduit
**pas** : une machine où PySide6 n'a jamais été installé pourrait échouer à l'import d'une
dépendance transitive que la nôtre a déjà. La CI, elle, mesure le vrai cas.

## 6. Critère 4 — et la réserve, parce que le plan demandait plus que ce qui est défendable

Le plan écrit : « **le LLM revient** : si la brique a déchargé `yume-27b` pour faire sa place,
elle le recharge à la fin, y compris sur annulation et sur erreur. »

**Appliqué à la lettre, ce serait un défaut.** Recharger ~17 Go de LLM pendant que ComfyUI
tient ses ~12 Go de transformeur est exactement le scénario que toute l'architecture refuse —
`docs/README.fr.md` (≈ l. 639) : « ~17 Go ne tiennent de toute façon pas dans 20 Go de VRAM.
Ça supprime tout scénario de seconde instance / partage de VRAM ».

Ce qui est livré est donc **plus étroit que le plan**, et le dire vaut mieux que de le faire
en silence :

| Situation | Ce qui se passe |
|---|---|
| `vram.decharger_image: false` (le défaut) | le LLM **n'est pas** rechargé, et la brique **le dit** |
| `vram.decharger_image: true` et le moteur a rendu la carte | le LLM revient |
| le moteur a planté en rendant la carte | rien n'est rechargé, le motif est journalisé, le run n'échoue pas |

**Conséquence : sur la configuration livrée, ce point du critère 4 n'a aucun effet.** Il est
livré armé (`recharger_llm: true`) mais conditionné à un réglage lui-même désarmé — la
politique du dépôt pour ce qui n'est pas soutenu par la mesure (`onomatopees.effacement.mode`,
`vram.decharger_image`).

Ce qui **est** pleinement tenu, en revanche : la bascule se ferme sur **tous** les chemins de
sortie, elle est **idempotente**, et chaque étape est isolée. Douze tests le vérifient, dont
deux qui traversent le vrai `phase_image` — l'un en faisant lever le moteur, l'autre en
annulant après deux images sur trois.

## 7. Ce que la mesure ne dit pas

C'est la section que `docs/mesures/webtoon-2026-08-26.md` a rendue obligatoire, et elle est
longue ici parce que ce lot est un lot d'interface.

1. **Aucun run GPU n'a eu lieu dans cette session.** Ni ComfyUI, ni poids d'image, ni carte
   graphique. Tout ce qui touche au GPU — la bascule, l'annulation, le déchargement, le
   rechargement — est vérifié avec des appelables **injectés** et le moteur factice. La chaîne
   est donc prouvée, **la génération ne l'est pas**, et les chiffres du §1 sont ceux des lots
   précédents, pas de celui-ci.
2. **L'écran de relecture n'a pas été essayé sur un vrai corpus par un humain.** Le lot 26
   avait montré que seul l'usage réel révèle certains défauts — « une revue en bloc ne vaut
   rien », découvert au premier personnage relu hors session de développement. Rien ne dit que
   cet écran-ci n'a pas son équivalent.
3. **Les trois verdicts affichés sur une vignette valent ce que vaut le juge du lot 25**, qui
   ne sépare « même personnage » de « personnages différents de la même œuvre » que **68 fois
   sur 100**. L'écran les montre avec le descripteur qui décroche plutôt qu'un score nu, ce
   qui les rend lisibles — pas plus fiables.
4. **La légende est vérifiée dans les trois formats sur un document témoin d'un chapitre**,
   pas sur un tome réel de 200 pages avec ses styles, ses dialogues et ses images de source.
   Rien n'indique un problème ; rien ne l'exclut non plus.
5. **Le placement « au début du premier chapitre qui nomme le personnage » est une heuristique
   de nom propre.** Elle a déjà été corrigée une fois pendant l'écriture du test : « Ai »
   répondait à « j'**ai** », parce que le `\w` de Python ne compte pas l'apostrophe comme une
   lettre. Elle reste faillible sur un homonyme, un surnom, ou un nom qui est aussi un mot
   commun. Le repli est nommé — tête de volume — et le rapport le dit.
6. **La propriété de feuille de `illustration/` a été affaiblie**, et le remplacement est plus
   faible que l'original : « aucun import de niveau module » plus un test d'exécution, au lieu
   de « aucun import du tout ». Un `getattr(importlib.import_module("illustration"), …)`
   passerait sous les deux radars.
7. **Le poids disque est une estimation par une médiane.** 2,1 Mo par PNG vient de onze
   images d'un seul run, à une seule résolution, avec un seul modèle. Un tome en couleurs, une
   autre résolution ou un autre quantifieur donneraient autre chose.
8. **`purger` ne fait pas de corbeille.** La suppression est définitive, la confirmation dit
   ce qu'elle détruit, et c'est tout ce que le lot promet.
9. **Le périmètre d'écriture de `frontiere.py` n'est PAS armé autour de « garder » ni de
   « jeter »**, et ce n'est pas un oubli : le garde refuse tout `.png` écrit hors de
   `marquage.ecrire`, donc un `shutil.move` d'une image déjà marquée lèverait
   `ImageNonMarquee` — alors qu'il ne produit rien, il déplace. Ce qui remplace le périmètre
   est plus étroit mais moins mécanique : les trois fonctions ne visent que des chemins que
   l'appelant leur donne, et les deux appelants du dépôt les prennent de
   `orchestrateur.dossier` / `dossier_retenues` / `dossier_rejetees`. Un troisième appelant
   distrait pourrait viser ailleurs, et rien ne l'arrêterait.

## 8. Le défaut du dépôt trouvé en chemin, et il n'était pas dans le plan

**Le `config.yaml` publié armait la brique d'illustration depuis la 2.20.0.**

`git diff 693a0c2 6779edc -- config.yaml` montre **six** valeurs changées qui n'ont aucun
rapport avec le lot « police » de ce commit :

| Clé | 2.19.1 | 2.20.0 (publié) | rétabli |
|---|---|---|---|
| `illustration.actif` | `false` | **`true`** | `false` |
| `illustration.moteur` | `"factice"` | **`"comfyui"`** | `"factice"` |
| `illustration.comfyui.workflow` | `qwen-image-2512-lightning` | **`qwen-image-edit-2511`** | lightning |
| `illustration.comfyui.timeout` | `600` | **`1200`** | `600` |
| `illustration.identite.actif` | `false` | **`true`** | `false` |
| `illustration.prompt.llm.actif` | `false` | **`true`** | `false` |

Ce sont les réglages de travail d'une machine, entrés par mégarde. Le dépôt **publiait** donc
une brique expérimentale armée, avec un moteur qui exige un serveur installé à la main et un
modèle de vision appelé à chaque image — sur toute installation neuve.

⚠ **Et le test qui devait l'attraper échouait déjà**, depuis ce jour-là :
`test_le_defaut_du_depot_est_bien_desarme` lit `git show HEAD:config.yaml` précisément pour
cette raison, et il était rouge sur `main`. Il l'était donc au moment où le lot 27 a commencé
— relevé dans la mesure de départ de cette session : **1 échec, 3 622 passés**. Un test rouge
qu'on laisse rouge apprend à ignorer les échecs, et c'est exactement ce que
`tests/README.md` refuse.

Les six valeurs sont rétablies. La leçon, elle, n'est pas dans le code : **relire le diff de
`config.yaml` avant un commit qui ne parle pas de configuration.**

## 9. Reproduire

```powershell
ruff check .
python -m pytest -q -m "not modeles and not lent"

# les comptes avec et sans Qt (le second bloque PySide6 par un meta_path)
python -m pytest --collect-only -q

# le chiffre de l'étape 0.1, le poids disque, et l'état de l'insertion
python run_illustration.py --check

# la galerie
python run_illustration.py "Mon LN" --inventaire
python run_illustration.py "Mon LN" --garder build/Mon_LN/illustrations/aya.png
python run_illustration.py "Mon LN" --purger

# l'atelier graphique
python gui.py            # onglet « Atelier »
```
