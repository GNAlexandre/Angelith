# Chiffres de référence

Ce document existe pour une raison simple : **plusieurs nombres circulaient pour le même
objet**, tous exacts, aucun avec son dénominateur écrit. 821, 813, 797, 790 et 687 bulles
désignaient le même tome ; 1 593 et 1 599 les deux tomes ensemble ; « un millier et demi » de
tests un dépôt qui en collecte plus de deux mille.

Aucun de ces chiffres n'était faux. Ils comptaient des choses différentes, à des dates
différentes, dans des fichiers différents. Ce qui manquait n'était pas la mesure : c'était la
**phrase qui dit ce qu'on compte**.

> **Règle du dépôt, à partir d'ici.** Tout chiffre de communication du projet — README,
> docstring, commentaire de configuration, entrée de changelog — porte **sa source** et **son
> dénominateur**. Un chiffre sans dénominateur n'est pas une mesure, c'est une impression.

---

## Comment les reproduire

```powershell
python tools/banc.py --tous                       # tous les volumes de build/
python tools/banc.py --tous --markdown > docs/banc-<date>.md
python tools/banc.py --tous --traduction          # le banc de traduction, sans appel LLM
python tools/banc.py --corpus tests/corpus/synthetique   # rappel / precision / F1
python tools/banc_sfx.py --tous                   # le TEXTE HORS BULLE (lot 21)
python tools/banc_sfx.py --tous --echantillon 60  # sa vérité terrain, graine 21
python -m pytest --collect-only -q                # le nombre de tests
```

`tools/banc.py` lit **uniquement** les caches sous `build/` : il ne charge aucun modèle et ne
réécrit rien (seul `--corpus` charge le détecteur, parce que mesurer un rappel demande de
détecter). Sa sortie `--markdown` porte la date, le commit et l'empreinte SHA-256 de
`config.yaml` : deux tableaux ne se comparent que si l'on sait ce qui a changé entre eux.

---

## Les sources, et ce que chacune compte

| Source | Ce qu'elle contient | Ce qu'elle ne contient PAS |
|---|---|---|
| `.checkpoints/page_XXXX/regions.json` | **la détection** : une entrée par région, avec `bbox`, `score`, `kind`, `scindee` | rien de l'OCR, du nettoyage ni du rendu |
| `.checkpoints/page_XXXX/qa.json` | le contrôle qualité d'une planche : nettoyage, OCR, traduction, rendu, zones restaurées | **les planches où il n'a pas été écrit** |
| `.checkpoints/page_XXXX/ocr.json` / `traduction.json` | les textes, alignés par POSITION sur `regions.json` | — |
| `pages_out/page_XXXX.png` | la planche rendue ; sur une planche à zéro bulle, la planche d'origine au pixel près | — |
| `RAPPORT.md` | tout ce qui précède, **par tome**, en prose | l'agrégation entre volumes, la date, le commit |

### Le piège n° 1 — compter les bulles depuis `qa.json`

C'est ce que fait `RAPPORT.md`, et c'est pourquoi il annonce **813** bulles là où
`regions.json` en porte **821** sur le tome de référence. L'écart de 8 tient dans **une seule
planche** : la page 8 n'a pas de `qa.json`, et elle porte exactement 8 bulles.

> ⚠ **Et la ligne du rapport se lisait de travers.** Son résumé écrit
> « ⚠ SANS contrôle qualité : 8 », où cette liste énumère des **numéros de planche**, pas un
> compte (`report_manga.py` y joint `sans_qa[:12]`). Il n'y a **pas** huit planches sans
> contrôle qualité : il y en a **une**. La coïncidence entre le numéro de la planche et le
> nombre de ses bulles rendait la méprise invisible — elle avait été reconduite jusque dans le
> plan de lot, et c'est le banc qui l'a levée.

Les deux nombres sont justes. Ils répondent à deux questions :

- **821** — *combien de bulles la détection a-t-elle trouvées ?* (`regions.json`)
- **813** — *combien de bulles ont été contrôlées ?* (`qa.json`)

`tools/banc.py` compte depuis `regions.json` et publie les planches sans `qa` dans une colonne
à part (`sans qa`). Les deux chiffres restent visibles ; ils ne se remplacent plus l'un
l'autre.

### Le piège n° 2 — `qa["sfx"]` pris pour un test d'encre

Pour trier les planches à zéro bulle entre « page de garde » et « pleine page d'action non
traduite », `report_manga.py` regarde `qa["sfx"]`. C'est correct **pour ce que le rapport
annonce** — mais la passe onomatopées est optionnelle
(`config.yaml > manga.onomatopees.actif`). Sur un tome traité sans elle, `qa["sfx"]` est vide
partout, et **aucune** planche à zéro bulle n'est triée : une page blanche et une page couverte
de katakana y comptent pareil.

Le banc mesure donc l'encre sur la planche elle-même et ne retombe sur `qa["sfx"]` qu'à
défaut. La colonne `source encre` dit toujours laquelle a répondu.

> **Mis à jour au lot 12.** Le calcul vit désormais dans **`manga/detection.py`**
> (`porte_de_l_encre`), et `tools/_banc_commun.py` s'y adosse plutôt que d'en garder une copie.
> Ce n'est pas un rangement : c'est **le même test** qui arme l'escalade de détection dans le
> pipeline et qui remplit la colonne « dont encrées » du banc. Un rapport qui trierait ses
> planches autrement que le pipeline ne mesurerait pas le pipeline.
>
> Deux changements mesurables l'accompagnent :
>
> · **Sous-échantillonnage ×4** (`Image.BOX`), parce que le test est maintenant posé sur chaque
>   planche d'un run et non plus sur les seules planches à zéro bulle d'un tableau.
>   **Iso-comportement vérifié** : sur les 145 planches à zéro bulle qui étaient déjà
>   mesurables, le verdict est inchangé pour **toutes**. Les quatre écarts avec la pleine
>   résolution tombent sur des planches de *manga D* Vol.1/Vol.2 qui n'étaient **pas
>   mesurables du tout** avant ce lot, et ils vont tous dans le sens « porte de l'encre » —
>   l'asymétrie voulue.
> · **Une quatrième source d'image**, `sources/`, après `pages_out/` et `pages_clean/`. C'est la
>   seule entorse au « cache-seul » du banc, et elle est en lecture. Sans elle, les
>   **43 planches** à zéro bulle des deux premiers volumes de *manga D* — qui n'ont ni
>   rendu, ni page nettoyée, ni `qa.json` — restent définitivement non mesurables.
>
> **Résultat : les 188 planches à zéro bulle sont désormais classées, toutes.** 183 portent de
> l'encre, 5 sont blanches, **0 non mesurée** (contre 140 / 5 / 43 au tableau du 2026-08-25).

⚠ Ce test dit « cette planche porte quelque chose », **pas** « cette planche porte du texte ».
Séparer le texte du dessin demanderait `text_detection`, donc 94,7 Mo de poids et une passe
ONNX par planche ; le banc publie ce qu'il mesure vraiment, et le nomme ainsi.

### ⚠ Une prémisse du plan de lot 12 était fausse : « couverture » n'est pas « page blanche »

Le plan annonçait que « les pages de garde et les couvertures de manga A (planches 1 à 4 et 147
à 150 de chaque tome) sont des négatifs attendus ». **Mesuré, c'est faux**, et l'erreur est
dans le libellé, pas dans le test : une couverture est une illustration pleine page.

| Planche | Part de pixels s'écartant du fond |
|---|---|
| manga A Vol.1 p1 (couverture) | **0,879** |
| manga A Vol.1 p3 | **0,890** |
| manga A Vol.4 p147 | **0,987** |
| manga A Vol.1 à Vol.4 **p2** (vrai séparateur) | **0,0025** |

Sur les quatre tomes, **un seul** de ces huit feuillets est réellement blanc : la planche 2, et
le test la classe correctement à chaque fois. Les autres portent de l'encre, et le test répond
donc juste à la question qu'on lui pose.

Ce que ça change pour l'escalade : elle tourne sur les couvertures et sur les liminaires
illustrés. Mesuré sur les quatre tomes de manga A — 29 planches liminaires à zéro bulle —, elle
en tire **6 bulles sur 5 planches** ; les 24 autres passent par `aucun_gain` ou par le véto
`aucune_nettoyable`.

⚠ **Ces 6 bulles n'ont pas été inspectées à l'œil, et il faut le dire.** Une couverture peut
porter un vrai cartouche de titre comme une fausse détection sur un aplat. Elles représentent
**6 des 47 bulles gagnées** par le lot ; le décompte principal — 35 planches réparées — n'en
dépend pas, mais un relecteur qui veut vérifier le lot commence par là. La sanction reste au
bon endroit : le nettoyeur refuse déjà de peindre une région dont l'uniformité tombe sous
`seuil_abandon`, et `RAPPORT.md` publie « zones restaurées » et « bulles sans texte OCR » —
c'est là qu'une fausse détection sur une couverture se verra, au premier run complet.

Le coût, lui, est **une inférence par couverture** — quatre par tome. C'est le bon arbitrage
compte tenu de l'asymétrie : un faux positif coûte une inférence, un faux négatif efface du
décompte une planche entièrement non traduite.

---

## Les chiffres qui circulaient, et leur dénominateur

### Bulles du tome de référence (*manga A*, Vol.1)

| Chiffre | Où il apparaît | Ce qu'il compte | Date de mesure |
|---|---|---|---|
| **821** | plan de lot `PLAN-00` (document de planification, hors dépôt) | régions de `regions.json`, toutes planches | 2026-08-24 |
| **813** | `RAPPORT.md` du tome | bulles de `qa.json` — la page 8, et elle seule, n'en a pas, avec ses 8 bulles | 2026-08-25, reproduit |
| **797** | `bubbles_split.py`, `config.yaml > manga.detection.scission` | régions du tome au moment de la mesure du lot 4.2 | lot 4.2 |
| **790** | `geometry.py`, `scinder_par_erosion` | présenté comme le **même** tome et les **mêmes** 40 candidats | lot 4.2 |
| **687** | `bubbles_split.py` | régions de plus de 20 000 px² — le sous-ensemble sur lequel porte la médiane de remplissage 0,89 | lot 4.2 |

> ✅ **Reproduit.** `python tools/banc.py --tous` rend **821** régions sur les 150 planches
> de *manga A* Vol.1, et **813** bulles portant un `qa.json` : le relevé manuel du 2026-08-24
> tombe juste. Le tableau daté est publié — [`banc-2026-08-25.md`](mesures/banc-2026-08-25.md) — et
> ses trois écarts avec les `RAPPORT.md` y sont **expliqués, pas absorbés** (§4).

**L'écart 797 / 790 n'est expliqué nulle part.** Il n'a pas été inventé pour ce document : les
deux chiffres décrivent la même mesure, sur le même tome, avec les mêmes 40 découpages
candidats. Il ne se tranche pas par relecture, il se tranche en remesurant — et c'est
précisément ce que `python tools/banc.py --tous` fait. Les deux emplacements se citent
désormais l'un l'autre et renvoient ici, plutôt que d'afficher chacun son nombre comme s'il
était seul.

### Régions des deux tomes

| Chiffre | Où | Dénominateur |
|---|---|---|
| **1 593** | `text_detection.py`, `core/version.py` | bulles des `qa.json` des deux tomes, **rendus de la v1.0.0** |
| **1 599** | plan de lot `PLAN-00` (hors dépôt) | régions des `regions.json` des deux tomes |

✅ **Reproduit le 2026-08-25** : 821 (Vol.1) + 778 (Vol.2) = **1 599**. Le relevé manuel tombe
juste.

Le chiffre historique de 1 593, lui, est **conservé** dans le code avec sa date et sa source :
il compte les bulles des `qa.json` sur les **rendus de la v1.0.0**, et les caches ont bougé
depuis (le même compte donne 1 591 aujourd'hui). Il documente une mesure passée ; il ne prétend
plus décrire l'état courant.

### Nombre de tests

| Chiffre | Où | Dénominateur |
|---|---|---|
| **5 025** | `README.md`, `CONTRIBUTING.md`, `docs/COMMANDES.fr.md` | `pytest --collect-only -q`, toutes dépendances optionnelles installées, 2026-09-06 |
| **4 968** | — | ce que la boucle courte exécute : `-m "not lent and not modeles"` |
| **57** | — | désélectionnés par ces marqueurs : 57 `lent`, dont 22 aussi `modeles` — tout ce qui exige les poids est aussi lent, l'inverse n'est pas vrai |
| **4 585** | `docs/mesures/creation-import-maj-2026-09-06.md` | le même total **sans PySide6**, soit un écart de **440** — `python -m pytest --collect-only -q -p tools.compte_sans_pyside`, 2026-09-06 |

⚠ Les nombres antérieurs (1 908, 1 657, « un millier et demi », 2 262, 2 909, 3 804, 3 809, 3 811, 3 868, 3 872, 3 969, 3 996, 3 998, 4 130, 4 239, 4 378, 4 487, 4 510, 4 567, 4 705, 4 846, 4 886, 4 912, 5 008, 5 019) n'étaient pas faux non
plus : ils dataient. Un compte de tests se périme à chaque commit — c'est pourquoi celui-ci
porte sa date, et pourquoi la commande qui le reproduit est écrite à côté.

> **Depuis le lot 20, ce tableau est la SOURCE et non plus un relevé parmi d'autres.**
> `tests/test_coherence_chiffres.py` lit ces lignes et vérifie que les trois fichiers de la
> colonne « Où » citent bien **ce** nombre **avec cette date**, et que l'arithmétique tient
> (4 968 + 57 = 5 025). La divergence à quatre chiffres qui a motivé ce document ne peut plus
> se reproduire en silence : elle colore un test en rouge.
>
> Reproduire les deux premiers : `python tools/compte_de_tests.py` et
> `python tools/compte_de_tests.py -m "not lent and not modeles"`.
>
> ⚠ **Le troisième dénominateur, celui de `ci.yml`, ne s'unifie PAS à ceux-ci** et le test ne
> le lui demande pas : `2 644 tests contre 2 504, soit 140` (2026-08-27) mesure l'**effet de
> l'installation de PySide6** dans la configuration de la CI — socle + GUI + dev, sans
> `requirements-manga.txt`. Il n'a de sens que par paire, et il n'a pas été remesuré au lot 20
> (voir [`atelier-github-2026-08-28.md`](mesures/atelier-github-2026-08-28.md)). Le test vérifie que
> son arithmétique tient et qu'il porte sa date, pas qu'il égale le total du dépôt.

### Le texte hors bulle (lot 21, 2026-08-28)

Deux nombres du dépôt étaient faux et sont corrigés ici, à leur source
(`config.yaml`, `manga/text_detection.py`) comme dans
[`sfx-2026-08-28.md`](mesures/sfx-2026-08-28.md).

| ce qu'on croyait | ce que la mesure donne | dénominateur |
|---|---|---|
| « 283 filigranes — 63 % » sur le *manga A* Vol.1 | **92 — 20,5 %** | 448 zones hors bulle du tome |
| « 105 sur 217 » sur le *manga B* | **0 sur 217** | idem |

Le 283 n'a jamais eu de dénominateur, et le commit qui l'a écrit (`772e5b7`) porte à trois
lignes d'écart la ventilation qui le contredit : 92 + 15 + 81 + 260 = 448. C'est l'exemple type
de ce que ce document existe pour empêcher.

Les chiffres neufs, avec leur dénominateur :

| chiffre | valeur | dénominateur |
|---|--:|---|
| lectures **exactes** de `manga-ocr` | **14,6 %** | 41 zones de l'échantillon dont la lecture nourrit le LLM (60 tirées, 7 mobilier jamais lu, 11 ponctuation sans appel, 1 écartée) |
| lectures « plausibles mais fausses » | 51,2 % | idem |
| zones qui sont réellement une onomatopée | 23 % | 60 zones de l'échantillon |
| zones qui avalent au moins la moitié d'une bulle | 25,7 % | **2 456** zones, 6 tomes |
| zones à encre claire | 13,6 % | 2 455 zones mesurables |
| uniformité du fond local ≥ 0,60 | 53,2 % | idem |
| zones de mobilier écartées | 335 | idem |

⚠ **La vérité terrain de l'échantillon a été transcrite par un modèle vision, pas par un
humain** ([`sfx-echantillon-2026-08-28.json`](mesures/sfx-echantillon-2026-08-28.json)). C'est écrit
dans le fichier et dans le document du lot ; une relecture humaine reste due.

### Licences des modèles

| Modèle | Licence | Relevé |
|---|---|---|
| `kitsumed/yolov8m_seg-speech-bubble` (détection de bulles) | **GPL-3.0** | 2026-08-25, page du modèle |
| `comic-text-detector` / `mayocream` (texte sur le dessin) | **GPL-3.0** amont, poids pour partie entraînés sur **Manga109-s** (usage académique) | 2026-08-16 |
| `kha-white/manga-ocr-base` (OCR japonais) | **Apache-2.0** | 2026-08-25, page du modèle |
| `JustANormalTinkerer/hayai-ocr-v2` (candidat onomatopées, **non employé**) | **Apache-2.0** | 2026-08-28, page du modèle — cf. `sfx-2026-08-28.md` voie B : licence propre, mais `safetensors` seulement (623 Mo, `trust_remote_code`), donc `torch` en dépendance dure |

Voir [`ai-provenance.md`](ai-provenance.md) et [`../manga_models/README.md`](../manga_models/README.md).

---

## Ce que ce document ne fait pas

Il ne mesure rien. Il dit **ce que chaque nombre compte** et **avec quelle commande le
refaire**. Le tableau daté, lui, est publié à part — `docs/banc-<date>.md`, produit par
`python tools/banc.py --tous --markdown` — parce qu'il change à chaque run et que celui-ci ne
doit pas changer.
