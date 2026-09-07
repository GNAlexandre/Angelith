# Le prompt vient de l'œuvre — et ce n'est pas sa FORME qui décide, c'est le CHOIX des images

**Date** : 2026-08-30 · **Version livrée** : 2.18.0 · **Branche** : `main` · **Commit de
départ** : `ef60334` (2.17.0)
**Machine** : AMD Radeon RX 7900 XT, **20 464 Mio** de VRAM, ROCm 7.14, Windows 11, 32 678 Mio
de RAM
**Pile** : ComfyUI **0.34.2** (torch 2.12.0+rocm7.14.0, Python 3.13.12), nœud `ComfyUI-GGUF`
**Modèle d'image** : `Qwen-Image-Edit-2511` GGUF **Q4_1**, encodeur `Qwen2.5-VL-7B` fp8, VAE
`qwen_image_vae`, LoRA `Qwen-Image-Edit-2511-Lightning-4steps` bf16 — toutes **Apache-2.0**
**Modèle de langue et de vision** : `yume-27b` (base Qwen 3.8 27B, IQ4_XS, 15,18 Go), capacité
`vision` confirmée par `ollama show`
**Juge d'image** : `dinov2-base` en ONNX (`onnx-community`), 346 627 111 octets
**Corpus** : `roman S` — bible du lot 23, **11 personnages**, 10 références validées, 16
illustrations exploitables au Vol.1
**Empreinte SHA-256 de `config.yaml` livré après le lot** :
`25fd55b59379f1114b5cf64c3e1f1540c413897a5ae28d2e40c9168f6274ac25`
(avant le lot : `9e559709885ed70a41e10688a5c08e6f9000aded45d9a027fe16517e364b9922`)
**Plan exécuté** :
[`docs/plans/PLAN-26-LE-PROMPT-VIENT-DE-L-OEUVRE.md`](../plans/PLAN-26-LE-PROMPT-VIENT-DE-L-OEUVRE.md)

> ⚠ **Les images ne sont pas dans ce document.** Le corpus est sous droits, et le
> `README-ILLUSTRATION-23-27` §5 n'autorise à montrer que celles de `Pride and Prejudice`,
> qui est du domaine public. On publie des **chiffres** et, quand l'œil est le seul
> instrument, **une ligne de description par image**.

> ⚠ **La configuration des mesures n'est pas celle qui est livrée**, et c'est délibéré :
> `config.yaml` est un DOCUMENT de 95 Ko de prose justifiée (interdit n° 5), qu'un aller-retour
> `yaml.safe_dump` effacerait. Les mesures ont tourné sur une copie portant **sept clés
> changées**, et les voici plutôt qu'une empreinte de fichier temporaire que personne ne
> pourra relire :
>
> ```yaml
> illustration.actif: true
> illustration.moteur: "comfyui"
> illustration.comfyui.workflow: "illustration/workflows/qwen-image-edit-2511.api.json"
> illustration.identite.actif: true
> illustration.identite.encodeur.fichier: "dinov2-base.onnx"
> illustration.prompt.style: "ancrages"      # pour POUVOIR mesurer l'approche 2
> illustration.prompt.ancrages_max: 1        # idem
> ```

---

## 1. Le verdict, en une page

Le `PLAN-26` demandait de mesurer **la forme du champ texte**. Le premier relevé réel a
répondu à une autre question, plus grande, et c'est elle qui commande ce lot.

| Ce qui était en jeu | Verdict | Où |
|---|---|---|
| **le matériau** — un prompt peut-il venir de l'œuvre ? | ✅ **oui, et largement** : 14 fragments cités sur 15 possibles pour 3 personnages, et le genre passe de 0/11 à **9/11** sans un appel de modèle | §2 |
| **le CHOIX des images** — quelle image montrer au modèle ? | ✅ **c'est le levier**, et il corrige le défaut que le lot 25 déclarait insoluble : le **régime de couleur** | §3 |
| **la forme du champ texte** — prose, catégories, JSON | ⚠ **écart faible et non concluant sur 3 images** ; le « +30 % » de la source communautaire n'est confirmé par rien ici | §5 |
| **français contre anglais** | ⚠ **mesuré sur un HYBRIDE**, et le dire fait partie du résultat | §6 |
| **le style** — mots, ancre, ou rien | ✅ **l'approche 1 gagne, et pour +25 jetons** : la signature mesurée mise en mots corrige elle aussi le régime de couleur. L'approche par **ancre** donne le meilleur écart moyen et ne corrige pas le régime : livrée **DÉSARMÉE** | §4 |
| **la reproductibilité** | ✅ **octet pour octet**, et quatre exécutions indépendantes de la même requête donnent la même mesure au centième | §9.1, §9.2 |
| **les canaux structurés** | ❌ **aucun livré**, licences vérifiées, coût VRAM **non mesurable** — et le dire est le résultat | §7 |
| **la porte humaine** | ✅ deux battants, deux tests, un refus avant la bascule VRAM | §8 |

**Ce qui a changé par rapport au lot 25, en une ligne** : les images générées sont maintenant
**en noir et blanc comme le tome**. Et ce lot a trouvé **deux leviers indépendants** pour
l'obtenir — ne plus montrer une couverture en couleur au modèle (§3), ou lui dire en toutes
lettres le registre que le lot 23 avait mesuré (§4). Le lot 25 écrivait « cinq images de plus
n'y changeront rien » : il avait raison, ce n'était pas une question de nombre.

---

## 2. Étape 0 — de quoi un prompt peut-il être fait, sur le corpus réel

Le plan pose la condition d'entrée sans détour : « S'il est majoritairement vide, ce lot n'a
pas son matériau et c'est le `PLAN-23` qu'il faut prolonger, pas celui-ci qu'il faut écrire. »

Il n'est pas vide.

### 2.1 — Les trois personnages, fragment par fragment

Les trois les mieux documentés de la bible, choisis par le banc et non à la main
(`tools/banc_prompt.py --fragments`) :

| personnage | fragment | source exacte | présent ? | valeur |
|---|---|---|---|---|
| Tory Noelle | age_apparent | bible.apparence + citations[] | ✅ | quinze ans |
| Tory Noelle | cheveux | bible.apparence + citations[] | ✅ | gris courts |
| Tory Noelle | yeux | bible.apparence + citations[] | ✅ | gris |
| Tory Noelle | tenue | bible.apparence + citations[] | ✅ | usés, barbouillés de boue |
| Tory Noelle | signes | bible.apparence + citations[] | ✅ | croix sur col, sang sur le visage, brassard croix |
| Tory Noelle | genre | bible.genre_confirme, sinon glossaire | ✅ | féminin (**glossaire**) |
| Tory Noelle | images de référence | bible.references[identite, humaine] | ✅ | 7 validée(s) sur 7 |
| Gale | age_apparent | bible.apparence + citations[] | ✅ | adulte |
| Gale | cheveux | bible.apparence + citations[] | ✅ | courts foncés |
| Gale | yeux | bible.apparence + citations[] | ✅ | clairs |
| Gale | tenue | bible.apparence + citations[] | ✅ | uniforme militaire |
| Gale | signes | bible.apparence + citations[] | ✅ | grain de beauté sous l'œil, cernes évidents |
| Gale | genre | bible.genre_confirme, sinon glossaire | ❌ | — |
| Gale | images de référence | bible.references[identite, humaine] | ✅ | 1 validée(s) sur 1 |
| Kayle | age_apparent | bible.apparence + citations[] | ❌ | — |
| Kayle | cheveux | bible.apparence + citations[] | ✅ | bruns courts |
| Kayle | yeux | bible.apparence + citations[] | ✅ | bleus |
| Kayle | tenue | bible.apparence + citations[] | ✅ | blouse blanche tachée |
| Kayle | signes | bible.apparence + citations[] | ✅ | masque de tissu |
| Kayle | genre | bible.genre_confirme, sinon glossaire | ✅ | masculin (**glossaire**) |
| Kayle | images de référence | bible.references[identite, humaine] | ✅ | 1 validée(s) sur 1 |

**14 fragments d'apparence cités sur 15 possibles.** Le seul vide est l'âge apparent de Kayle,
et le cadrage n'est pas une case vide : il ne vient jamais du texte, c'est un choix de
l'utilisateur, et le plan l'écrit lui-même.

### 2.2 — Le résultat qui n'a coûté aucun appel de modèle

| | valeur |
|---|---:|
| `bible.genre_confirme` rempli | **0 / 11** |
| genre résolu en ajoutant `glossaire.personnages[].genre` | **9 / 11** |

Un champ que la bible ne remplit **jamais** et qu'un autre fichier du même dépôt porte déjà
n'est pas une donnée manquante : c'est une donnée qu'on n'allait pas chercher. Le lot 25 en
avait la trace à l'œil — « Gale », sans genre, était sorti en femme.

⚠ **Les deux sources ne disent pas la même chose et ne sont pas interchangeables.**
`bible.genre_confirme` est confirmé **sur un dessin** ; `glossaire.genre` est établi **sur le
texte**, et c'est lui qui commande déjà les accords de toute la traduction. La bible passe
donc en premier, le glossaire en second, et **le sidecar de chaque image dit lequel a parlé**.
Un `'?'` de glossaire — c'est le cas de Gale et de Salsa — ne devient pas un genre :
`core/bible.py` note qu'« une valeur fausse ici coûte plus qu'une valeur absente ».

### 2.3 — Ce que le matériau ne porte PAS

- **`bible.style.mots` est VIDE** sur ce corpus. L'approche 1 de l'étape 0.2 (« les mots »)
  n'aurait donc ajouté **aucun mot**, et la mesurer serait revenu à mesurer l'approche 3
  (« ne rien faire ») une seconde fois. C'est pourquoi ce lot **met la signature mesurée en
  mots** (§4.1) plutôt que de publier une colonne vide.
- **`bible.references[].cadre` est vide sur les 10 références** — le champ ajouté par le
  lot 25 pour porter un recadrage n'a toujours été rempli par personne. L'axe « nature du
  recadrage » de `PLAN-25` L25.1 reste donc non mesuré, pour la deuxième fois.
- **Le lexique de `core/bible_texte.py` n'est pas réutilisable** pour la clause de scène : il
  cherche les phrases qui parlent de cheveux et d'yeux, exactement celles dont la clause de
  scène ne veut pas. `illustration/scene.py` cherche les phrases qui **nomment** le
  personnage. Se tromper de lexique aurait produit des clauses systématiquement rejetées, et
  le rejet aurait eu l'air d'un défaut du filtre.

---

## 3. L26.0 — le choix des images, et c'est LE résultat du lot

### 3.1 — Le modèle de vision lit ce que le classifieur ne voit pas

`yume-27b` reçoit une illustration à la fois, avec l'usage demandé, et rend trois lignes :
`retenue`, `visage`, `motif`. Un appel par image — le lot le plus petit possible, parce que
`num_ctx` vaut 32 768 et que vingt illustrations n'y entrent pas.

Sur les **10 références validées** du corpus et les **3 ancrages** de style, **13 appels,
64,0 s au total, 4,9 s par image**. Voici ce qu'il dit, et ce que l'œil confirme :

| image | classe de `core/illustrations.py` | motif du modèle de vision | vérifié à l'œil |
|---|---|---|---|
| `…Volume_1_p208_x1242` | `pleine_page` | « visage net, mais **page de couverture avec titre et nom d'auteur** » | ✅ **c'est la couverture du Vol.1**, titre, auteur, illustrateur et numéro compris |
| `…Volume_1_p206_x1238` (seule réf. de Gale) | `pleine_page` | « **page Afterword avec texte, titre et signature**, portrait noyé dans la composition » | ✅ c'est la page *Afterword*, avec le mot de l'illustrateur et sa signature |
| `…Volume_2_p2_x197` (seule réf. de Kayle) | `indeterminee` | « **visage masqué**, composition chargée, personnage noyé dans la scène » | ✅ scène à six personnages, texte anglais incrusté, Kayle porte un masque |
| `…Volume_2_p23_x330` (seule réf. d'Isaac Fenn) | `pleine_page` | « **deux personnages**, visage du barbu net mais composition partagée » | ✅ exact — mais le refus est **contestable**, le visage EST net et isolable |
| `…Volume_2_p167_x1024` | `pleine_page` | « visage de face net, personnage occupe la pleine page » | ✅ **portrait seul, au trait, en noir et blanc, fond blanc** |
| les 3 ancrages de style | `pleine_page` | « **deux visages humains nets et lisibles** » (les trois) | ✅ les trois portent des visages |

**Quatre motifs vérifiés à l'œil sur quatre sont factuellement exacts.** Le cinquième — le
refus d'Isaac Fenn — est exact dans sa description et discutable dans sa conclusion : le modèle
est **strict**, et cette sévérité a un coût mesuré au §3.3.

⚠ **Ce que cela dit du classifieur déterministe du lot 23.** `core/illustrations.py` range en
`couverture` les fichiers `p1` de chaque tome — **2 sur ce corpus** — et manque au moins trois
autres pages typographiées, dont la couverture du Vol.1 elle-même, qui porte le numéro `p208`.
Le mécanisme « repousser les couvertures en queue » du lot 25 ne pouvait donc pas fonctionner
sur les images qui en avaient le plus besoin. **C'est un défaut du lot 23 que seul l'usage
pouvait révéler**, et il n'est pas corrigé ici : il est **contourné** par un modèle de vision,
ce qui n'est pas la même chose et ne doit pas se lire comme tel.

### 3.2 — L'accord entre les deux sélections

| | valeur |
|---|---:|
| images jugées pareil par les deux | **26 / 43** |
| images retenues par le déterministe, refusées par la vision | **16** |
| images refusées par le déterministe, retenues par la vision | **1** |

⚠ **Un accord parfait n'aurait pas été une bonne nouvelle** : il voudrait dire que l'appel de
vision coûte du temps sans rien décider. Un désaccord n'en est pas une non plus tant qu'un
humain n'a pas tranché. Ce tableau **pose une question**, et la porte humaine de `requete.yaml`
est faite pour la refermer — c'est pour cela que chaque image y porte son motif.

### 3.3 — Ce que la sévérité du modèle coûte

| personnage | réf. validées | retenues par le déterministe | retenues par la vision |
|---|---:|---:|---:|
| Tory Noelle | 7 | 2 | **1** |
| Gale | 1 | 1 | **0** |
| Isaac Fenn | 1 | 1 | **0** |
| Kayle | 1 | 1 | **0** |

**Trois personnages sur quatre perdent leur seule référence**, et ne produisent donc **aucune
image** — le critère 5 du `PLAN-25` refuse de générer sans référence validée, et il n'a pas de
nuance. Le modèle a raison sur les faits (ce sont bien une page *Afterword*, un visage masqué,
une composition à deux) et son refus est **utilisable comme un diagnostic de la bible** : ces
trois personnages n'ont pas de bonne référence d'identité, et aucun prompt n'y changera rien.

⚠ **C'est pourquoi le choix par le modèle est livré DÉSARMÉ**
(`illustration.prompt.llm.actif: false`). Armé, il fait passer le corpus de 4 personnages
illustrables à 1. Ce n'est pas une régression — c'est une mesure de la qualité du corpus — mais
ce n'est pas un défaut à imposer par défaut à quelqu'un qui n'a rien demandé.

### 3.4 — Et voici ce que ce choix change dans l'image

Une seule variable change entre ces deux lignes : **quelles images sont montrées au modèle**.
Même personnage, même graine (1234), même prompt à la désignation des références près, mêmes
dimensions, même nombre de pas, même workflow.

| sélection | réf. | jetons du prompt | secondes | VRAM résidente (Mio) | ressemblance (non opposable) | nouveauté | style (descripteurs) | descripteur qui décroche | **même régime de couleur** |
|---|---:|---:|---:|---:|---:|---:|---:|---|---|
| **déterministe** (couverture + page à texte) | 2 | 79 | 278,3 | 12 070 | 0,44 | 0,44 | 0,12 | part_aplats | **non ✗** |
| **modèle de vision** (portrait au trait) | 1 | 67 | 83,9 | 11 403 | 0,57 | 0,43 | 0,13 | part_aplats | **oui ✅** |

> **Le régime de couleur bascule.** Le lot 25 avait écrit : « les générations sont en couleur,
> le tome est en noir et blanc, et **cinq images de plus n'y changeront rien** ». Il avait
> raison sur le mécanisme et tort sur la conclusion : ce n'est pas le nombre d'images qui
> compte, c'est **lesquelles**.

Ce que l'œil voit, une ligne par image :

| sélection | ce que l'image montre |
|---|---|
| déterministe | un portrait **en couleur**, propre, cadré au buste, uniforme boueux, croix au col et brassard — mais dans un registre de couverture, pas dans celui du tome |
| vision | **le même personnage en noir et blanc, au trait**, éclaboussé de boue et de sang, dans le registre exact des illustrations intérieures |

⚠ **Et l'écart moyen aux descripteurs ne bouge PAS** — 0,12 contre 0,13. Une moyenne qui reste
identique pendant qu'un descripteur binaire bascule est exactement ce que le critère 4 ter du
`PLAN-25` interdit de moyenner : le régime de couleur n'est pas une nuance de la moyenne, c'est
la différence entre « une image de cette œuvre » et « une image d'une autre œuvre ».

⚠ **Dénominateur : un personnage, une graine, deux images.** Rien ici ne se généralise à un
autre personnage — les trois autres n'ont qu'une référence, et la vision la leur refuse.

⚠ **Un facteur reste confondu, et il faut le dire** : la ligne « vision » a **une** référence,
la ligne « déterministe » en a **deux**. L'axe du nombre de références a été balayé au lot 25
(§5.4 : « la rupture est entre 1 et 2 ») et il concluait qu'à une seule référence le modèle
rend un **collage**. Ce n'est pas ce qui se produit ici — l'image à une référence est la bonne.
La différence est donc bien la **nature** de la référence et non son nombre, ce qui est
précisément la conclusion que le lot 25 avait tirée sans pouvoir la mesurer. Mais un balayage
propre demanderait deux bonnes références, et **le corpus n'en a pas**.

---

## 4. Étape 0.2 — comment le registre graphique entre dans la requête

### 4.1 — L'approche 1 a été rendue mesurable avant d'être mesurée

`bible.style.mots` est vide sur ce corpus : injecter « les mots » n'aurait rien injecté. Ce
lot ajoute donc `illustration/prompt.py:mots_de_signature`, qui traduit la **signature mesurée
par le lot 23** en mots dicibles à un modèle d'image.

Sur ce tome, mesuré sur ses **16** illustrations exploitables :

| descripteur | valeur mesurée | mot produit |
|---|---:|---|
| régime de couleur | `false` | **en noir et blanc** |
| saturation moyenne | 0,0661 | palette désaturée |
| densité de trait | 0,2664 | trait marqué, dessin très travaillé |
| part d'aplats | 0,3669 | larges aplats uniformes |
| contraste | 0,2421 | *(rien — sous le seuil)* |

⚠ **Le descripteur est MESURÉ, le seuil ne l'est pas.** Les seuils sont posés en tiers de
l'échelle [0, 1], écrits dans `SEUILS_REGISTRE` pour qu'on puisse les contester, et ce document
ne les présente pas comme une mesure. Ce qui se mesure, c'est **l'effet de la phrase sur
l'image produite**, et c'est le tableau qui suit.

### 4.2 — Le balayage

Trois approches, une seule variable changée : **comment le registre du tome entre dans la
requête**. Mêmes références (les deux du choix déterministe), même graine, même graphe.

| approche | jetons | secondes | ressemblance (non opposable) | nouveauté | style (descripteurs) | descripteur qui décroche | **même régime de couleur** |
|---|---:|---:|---:|---:|---:|---|---|
| **3 — ne rien faire** | 79 | 104,4 | 0,44 | 0,44 | **0,12** | part_aplats | **non ✗** |
| **1 — les mots de la signature mesurée** | 104 | 119,3 | 0,47 | 0,42 | **0,11** | part_aplats | **oui ✅** |
| **2 — une ancre de style sur le canal d'images** | 107 | 324,1 | 0,48 | 0,43 | **0,10** | part_aplats | **non ✗** |

> **Les mots suffisent à faire basculer le régime de couleur.** C'est le second levier trouvé
> par ce lot sur le défaut que le lot 25 déclarait insoluble, et il est indépendant du
> premier : ici les références n'ont pas changé — ce sont toujours les couvertures en couleur
> — et pourtant l'image sort en noir et blanc.

Descripteur par descripteur, les trois cas ne se valent pas :

- **l'approche 1 est la seule qui corrige le régime de couleur**, pour **+25 jetons** et
  aucune image de plus dans le canal ;
- **l'approche 2 donne le meilleur écart moyen** (0,10) et **ne corrige pas** le régime : une
  ancre au trait noir et blanc, placée en image 3 derrière deux couvertures en couleur, ne
  renverse pas ce que les deux premières imposent ;
- elle coûte en outre **une place du canal** — le graphe livré en expose trois, dont deux sont
  prises par l'identité — et **2,7 fois plus de temps** sur ce relevé.

**Approche retenue : la 1.** `illustration.prompt.style` vaut `"mots"`, et
`illustration.prompt.ancrages_max` vaut **0** — l'approche 2 est **livrée DÉSARMÉE**. Le
mécanisme est complet et testé ; ce qui n'est pas soutenu par la mesure est livré éteint, comme
`manga.onomatopees.effacement.mode: "aucun"` (lot 22) et `illustration.vram.decharger_image`
(lot 24).

⚠ **Une ligne de ce tableau a dû être reprise, et le dire fait partie de la mesure.** Le
premier relevé donnait à l'approche 1 un prompt **identique** à celui de l'approche 3 : sur ce
corpus `bible.style.mots` est vide, et « injecter les mots » n'injectait rien. Le tableau
affichait alors deux fois 79 jetons, et ComfyUI — qui met en cache l'exécution d'un graphe
identique — avait rendu la seconde image en **1 seconde**. Une ligne de tableau qui mesure deux
fois la même chose est pire qu'une ligne absente : elle a l'air d'un résultat. C'est ce défaut
qui a fait écrire `mots_de_signature`.

⚠ **Et le même cache a piégé la relance.** Après un `/interrupt` envoyé à ComfyUI, la reprise
du balayage a reçu en **1,1 s** le résultat *interrompu* du graphe précédent — une image
partiellement débruitée, mesurée à 0,23 d'écart de style au lieu de 0,12. La ligne
« ne rien faire » publiée ci-dessus est donc celle du **premier** relevé, et elle est
comparable : le prompt est byte-à-byte identique (vérifié), et la même requête a été exécutée
**quatre fois** dans cette session avec le même résultat au centième près — voir §9.1.

⚠ **Dénominateur : un personnage, une graine, trois images.** Le plan en demandait dix.

---

## 5. Étape 0.3 — les trois formes du champ texte

Mêmes fragments, même ordre, même sujet, même cadrage, même graine, mêmes références : seule
la **mise en forme** change. C'est la condition pour que la mesure porte sur la forme et non
sur ce qu'on a dit, et un test la garantit
(`test_les_trois_formes_portent_le_MEME_contenu`).

| forme | jetons du prompt | caractères | secondes | ressemblance (non opposable) | nouveauté | style (descripteurs) | descripteur qui décroche | même régime de couleur |
|---|---:|---:|---:|---:|---:|---:|---|---|
| **prose** | **79** | 319 | 104,2 | 0,44 | 0,44 | **0,12** | part_aplats | non ✗ |
| **catégories étiquetées** | 87 | 349 | 101,1 | 0,46 | 0,42 | **0,11** | part_aplats | non ✗ |
| **JSON sérialisé** | **95** | 380 | 103,3 | 0,43 | 0,46 | **0,12** | part_aplats | non ✗ |

**Verdict : aucun écart mesurable sur ce corpus.** Les trois valeurs de style tiennent dans
0,01 ; les trois valeurs de ressemblance dans 0,03, sur une grandeur que le lot 25 a déclarée
non opposable. Et ce que l'œil voit va dans le même sens : **trois images du même personnage,
même cadrage, même palette**, dont les différences se comptent en position de brassard et en
teinte de croix.

Ce qui **est** mesurable, c'est le coût :

| forme | jetons | par rapport à la prose |
|---|---:|---:|
| prose | 79 | — |
| catégories | 87 | **+10 %** |
| JSON | 95 | **+20 %** |

> **Le JSON coûte 20 % de jetons de plus et ne rend rien de mesurable en échange.** C'était
> l'hypothèse à tester, et la réponse est celle que la mécanique laissait attendre : accolades,
> guillemets et clés consomment le budget de l'encodeur sans porter de structure qu'un
> encodeur de vision-langage sache lire.

⚠ **Le « +30 % de précision » de la source communautaire n'est confirmé par rien ici**, et il
n'est recopié nulle part dans ce dépôt comme un fait : c'est l'affirmation d'un article de
blog, sans corpus ni dénominateur. Les catégories font **0,11 contre 0,12** en écart de style,
soit un point de pourcentage sur **une** image — ce qui n'est pas un résultat, c'est du bruit.

⚠ **Dénominateur : un personnage, une graine, trois images.** Le plan en demandait dix. Une
différence réelle de quelques pour cent ne se verrait pas à ce dénominateur, et ce tableau
**ne dit donc pas** que les trois formes sont équivalentes : il dit que sur ce corpus, à cette
taille d'échantillon, **rien ne permet de les départager** — et que la prose est la moins
chère.

**Défaut retenu : `prose`.** Elle est la moins coûteuse en jetons, elle est ce que la
discussion amont de `Qwen-Image-Edit-2511` recommande, et rien ici ne justifie de payer plus.

---

## 6. Critère 7 — français contre anglais

⚠ **Ce qui est mesuré n'est PAS « français contre anglais », et il faut le dire avant le
tableau.** Les VALEURS d'attribut viennent de `bible.yaml`, donc de la langue de traduction du
tome. Un prompt `en` sur une bible française est un **hybride**. Voici celui qui a été envoyé,
mot pour mot :

```
a lone woman, bust shot, framed at mid-body, against a plain background. quinze ans,
gris courts hair, gris eyes, wearing usés, barbouillés de boue, croix sur col, sang sur
le visage, brassard croix. The character is the one shown in image 1, image 2: keep their
face, hair and outfit, consistent across these images.
```

Ce n'est pas un défaut d'implémentation : faire traduire les attributs par un modèle
violerait le critère 4 du plan — les attributs viennent de la bible, mot pour mot. **C'est ce
que le dépôt peut livrer**, et le mesurer sans le dire aurait publié « anglais » pour autre
chose.

| langue de la charpente | jetons | secondes | ressemblance (non opposable) | nouveauté | style (descripteurs) | même régime de couleur |
|---|---:|---:|---:|---:|---:|---|
| **fr** | 79 | 105,3 | 0,44 | 0,44 | **0,12** | non ✗ |
| **en** (hybride) | 79 | 102,2 | 0,48 | 0,41 | **0,12** | non ✗ |

**Verdict : aucun écart mesurable, et la charpente anglaise ne casse rien.** L'écart de style
est nul à la quatrième décimale près ; l'écart de ressemblance (0,04) porte sur une grandeur
non opposable. À l'œil, deux images du même personnage, même cadrage, même palette.

Le fait le plus intéressant du tableau n'est pas un chiffre : **le modèle a honoré sans
broncher un prompt dont la moitié des mots est dans une autre langue que sa charpente.** C'est
cohérent avec ce que la carte de `Qwen-Image-Edit-2511` annonce d'un encodeur multilingue, et
c'est ce qui rend l'hybride livrable plutôt que théorique.

**Défaut retenu : `fr`.** Non pas parce que le français gagne — il ne gagne pas —, mais parce
qu'il est **cohérent** : la bible, le glossaire et le gabarit parlent alors la même langue, et
un utilisateur qui relit `requete.yaml` lit un texte entier plutôt qu'un hybride. Rien dans
cette mesure ne justifie de payer le coût de lisibilité d'un prompt mi-anglais mi-français.

⚠ **Dénominateur : un personnage, une graine, deux images.** Le plan en demandait dix.

---

## 7. Étape 0.4 — les canaux structurés, inventoriés à la source

Relevé sur le serveur réel (`/object_info`, **907 nœuds exposés**, ComfyUI 0.34.2), pas lu
dans une page web : une page amont peut annoncer un canal que l'installation locale n'a pas.

| canal | argument | ce qu'il apporte | nœud exposé ? | poids en plus | licence | état |
|---|---|---|---|---|---|---|
| images de référence | `TextEncodeQwenImageEditPlus` | **l'identité** | ✅ oui | aucun | **Apache-2.0**, vérifiée à la source le 2026-08-29 | **LIVRÉ**, mesuré au lot 25 et ici |
| entités + masques | `eligen_entity_prompts` + `eligen_entity_masks` | la **position et la forme** | ❌ **non** | LoRA `Qwen-Image-EliGen-V2`, 0,2 Md | **Apache-2.0**, vérifiée à la source le 2026-08-30 | candidat **non livré** — aucun nœud ne l'expose |
| image de contrôle | `ModelPatchLoader` → `QwenImageDiffsynthControlnet` | la **pose** | ✅ oui | un `MODEL_PATCH` blockwise (~1 Md) | **Apache-2.0**, vérifiée à la source le 2026-08-30 | candidat **non livré** — `ModelPatchLoader` expose une liste de poids **VIDE** |
| couches | `EmptyQwenImageLayeredLatentImage` | une sortie en calques | ✅ oui | `Qwen-Image-Layered` | non instruite | **hors périmètre**, le plan l'écrit |

**Aucun canal structuré n'est livré**, et le périmètre du plan l'autorise explicitement : « les
images de référence (acquises) + **un** canal structuré au plus, celui dont l'apport est
mesuré. Les autres sont documentés comme candidats, non livrés. »

⚠ **Le « coût VRAM mesuré » que le plan demande n'a PAS pu l'être, et voici pourquoi.** Aucun
de ces poids n'est installé : `ModelPatchLoader` expose une liste vide, et aucun nœud EliGen
n'existe sur ce serveur. Les mesurer aurait demandé de télécharger des poids **dont l'apport
n'est pas mesuré non plus** — l'ordre exact que le plan interdit (« un canal dont l'apport
n'est pas mesuré est un canal qu'on ne livre pas »).

Ce qui **est** mesuré, et qui décide en pratique : la **marge**. Après une génération réelle,
il reste **11,4 à 12,1 Go résidents** sur les 20 464 Mio de la carte, soit **8,4 à 9,1 Go
libres**. Un `MODEL_PATCH` d'environ 1 Md y tiendrait. Un canal se juge sur cette marge, pas
sur une taille de fichier annoncée.

⚠ Les champs `canaux.entites` et `canaux.image_de_controle` **existent quand même dans
`requete.yaml`**, vides et nuls. C'est la règle du glossaire et de la bible — « ce qui est
visible se corrige, ce qui est absent s'oublie » — et le moteur refusera le canal avec un
motif nommé si le graphe ne le porte pas.

---

## 8. La porte humaine — deux battants, et le second est neuf

| battant | ce qu'il refuse | où il tombe |
|---|---|---|
| `valide: false` (lot 24) | personne n'a validé le prompt | avant tout |
| `validation.par` vide (lot 24) | le sidecar ne pourrait pas dire QUI | avant tout |
| **toutes les références décochées** (lot 26) | l'humain a retiré ce que la phase 1 avait retenu | **avant la bascule VRAM** |

Le second battant se distingue du refus du lot 25, et la distinction est la raison d'être de
`validation.references_initiales` :

| dans le fichier | ce que ça veut dire | qui refuse |
|---|---|---|
| la phase 1 avait retenu, l'humain a tout décoché | « je ne veux plus de références » | `exiger_references_retenues`, tout de suite |
| la phase 1 n'avait rien retenu | la bible ne documente pas ce personnage | `identite.SansReferenceValidee` — refuse **cette image**, pas le run |

Les confondre ferait échouer un run entier pour le cas **majoritaire** du corpus : 7
personnages sur 11 n'ont aucune référence validée.

Deux tests le couvrent, comme le critère 1 ter le demande :
`test_la_phase_image_REFUSE_quand_toutes_les_references_sont_decochees` et
`test_un_personnage_qui_n_avait_AUCUNE_reference_ne_declenche_pas_ce_refus`.

---

## 9. Le run complet, de bout en bout

La chaîne entière a tourné sur le corpus réel, chemin nominal, modèle de vision **armé** :

```
python run_illustration.py "roman S" Vol.1 --phase prompt --ecraser   # 298,4 s
       … la porte : valide=true, validation.par renseigné …
python run_illustration.py "roman S" Vol.1 --phase image              # 718,3 s, 1 image
python run_illustration.py --rejouer …/tory-noelle.png.provenance.json
```

Ce que le run a fait, ligne par ligne :

| étape | résultat |
|---|---:|
| personnages candidats | 11 |
| retenus après le **plafond de budget** (8 par run) | **8**, motif nommé au journal et dans `RAPPORT.md` |
| clauses de scène produites par le LLM | **2** sur 6 tentatives (4 fois `RAS`) |
| personnages **refusés** faute de référence validée retenue | **7**, motif `sans_reference_validee` |
| images produites | **1** (`tory-noelle.png`) |
| bascule VRAM (déchargement du LLM) | **2,0 s** |
| rejeu depuis le sidecar seul | **octet pour octet identique** |

Ce que l'œil voit sur l'unique image produite : **un portrait en buste, en noir et blanc, au
trait**, du bon personnage, avec la croix au col, le brassard et les éclaboussures de boue —
c'est-à-dire le registre exact des illustrations intérieures du tome.

⚠ **Sept refus sur huit blocs n'est pas une panne, c'est le corpus.** Le modèle de vision
écarte les références qui sont des couvertures, des pages à texte ou des compositions à deux ;
la bible n'en propose pas d'autres pour ces personnages. Le critère 5 du `PLAN-25` refuse alors
de produire, et il n'a pas de nuance.

⚠ **Les clauses de scène sont bonnes, et elles n'ont servi à rien ici** : les deux personnages
pour lesquels le modèle a vu une pose — « Sorti de la tranchée, il tient son miroir de
reconnaissance, le visage las, sous la pluie » — sont justement des personnages sans référence
validée. Leur image n'a pas été produite. L'apport de la clause de scène reste donc **non
mesuré**.

### 9.1 — La reproductibilité, mesurée quatre fois plutôt qu'une

La requête « Tory Noelle, prose, français, aucun style, 2 références déterministes, graine
1234 » a été exécutée **quatre fois** dans cette session, par quatre commandes différentes :

| exécution | secondes | ressemblance | nouveauté | style (descripteurs) |
|---|---:|---:|---:|---:|
| `forme-prose` | 104,2 | 0,44 | 0,44 | 0,12 |
| `langue-fr` | 105,3 | 0,44 | 0,44 | 0,12 |
| `style-aucun` | 104,4 | 0,44 | 0,44 | 0,12 |
| `references-deterministe` | 278,3 | 0,44 | 0,44 | 0,12 |

**Les trois grandeurs sont identiques à la deuxième décimale sur les quatre.** C'est un
résultat plus fort qu'un `--rejouer` isolé : il porte sur quatre processus distincts, à des
heures différentes, avec des états de VRAM différents — ce que la colonne `secondes` montre
d'ailleurs, avec un facteur 2,7 entre la première et la dernière.

### 9.2 — `--rejouer`, critère 6

```
Rejeu écrit : build\roman S\Vol.1\illustrations\tory-noelle.rejeu.png
  → octet pour octet identique à l'original.
```

**Depuis le sidecar seul, la même image est reconstruite.** Le lot 24 avait laissé la question
ouverte en écrivant « la plupart des backends de diffusion ne sont pas déterministes » ; sur
cette pile — ComfyUI 0.34.2, ROCm 7.14, graphe d'édition, graine fixe — ils le sont.

⚠ **Ce que le sidecar seul ne rejoue PAS** : la phase 1. Le bloc `prompt_source` ajouté par ce
lot porte le gabarit **et son empreinte SHA-256**, la forme, la langue, le cadrage et la source
de chaque attribut — de quoi savoir d'où venait le prompt, pas de quoi le recalculer sans la
bible. Un gabarit nommé mais édité depuis produirait un autre prompt sous le même nom, et
c'est exactement ce que l'empreinte rend détectable.

### 9.3 — Critère 1 quater : la phase 1 face à la phase 2

| | secondes | dénominateur |
|---|---:|---|
| phase 1, **déterministe** | **0,09** | 11 personnages, 43 images candidates, aucun réseau |
| phase 1, **modèle de vision** (choix d'images seul) | **64,0** | 13 appels, 4,9 s par image |
| phase 1, **run complet** (choix + clauses de scène) | **298,4** | 13 appels de vision + 6 de texte |
| bascule VRAM | **2,0** | 1 modèle LLM déchargé |
| phase 2 | **718,3** | 1 image |

**La phase 1 pèse 29,4 % du run complet.** Elle ne coûte donc pas plus cher que la phase 2 —
le cas que le plan demandait de publier ne se produit pas ici — mais elle en est **le tiers**,
ce qui n'est pas négligeable et croîtrait avec le nombre d'illustrations du tome, pas avec le
nombre d'images demandées.

⚠ **Une inefficacité a été trouvée et corrigée pendant la mesure.** La première version jugeait
les ancres de style **une fois par personnage** : 11 × 3 = 33 appels là où 3 suffisent, une
ancre décrivant le registre de l'ŒUVRE et non d'un personnage. Le relevé publié est celui
d'après correction — **13 appels de vision** au lieu de 43.

⚠ **Un défaut de comptage a été trouvé et corrigé après ce relevé** : `phase1.appels_llm` ne
comptait que les appels de **vision**, pas les 6 appels de **texte** des clauses de scène. Le
run publié ci-dessus affiche donc « 13 appels » pour une phase 1 qui en a fait **19**. Le
correctif est livré ; le chiffre du tableau est celui du run, avec sa correction écrite à côté
plutôt qu'appliquée en silence.

⚠ **Les 718,3 s de la phase 2 sont un cas défavorable, pas une moyenne.** Le LLM local
occupait encore la carte quand la génération a démarré — 150 s par pas de débruitage contre
16 à 20 s en régime chaud. Le lot 24 avait déjà mesuré ce basculement à un facteur **9,6**.
La bascule VRAM a bien lieu (2,0 s) mais Ollama ne rend pas la mémoire instantanément.

### 9.4 — Deux pièges de ComfyUI, mesurés et publiés

1. **Le cache d'exécution peut rendre le résultat d'un run INTERROMPU.** Après un
   `POST /interrupt`, une requête au graphe identique a été servie en **1,1 s** avec l'image
   partiellement débruitée du run avorté. Rien ne le signale côté client : le `/history` rend
   une image, elle est marquée et écrite comme les autres. Seule sa mesure de style —
   **0,23 au lieu de 0,12** — a trahi la substitution.
2. **Interrompre coûte un rechargement de modèle.** Le même `/interrupt` a provoqué une
   réinitialisation de **22 minutes** au run suivant, qui a fait expirer le délai de 600 s du
   client. Le délai des mesures a été porté à 2 400 s, et le principe retenu est de **laisser
   la file se vider** plutôt que d'interrompre.

---

## 10. Les critères du plan, un par un

| # | Critère | Verdict |
|---|---|---|
| 1 | Le tableau de l'étape 0 est publié pour 3 personnages, fragment par fragment, avec ses vides | ✅ §2.1, et il est **plein** : 14 fragments cités sur 15 |
| 1 bis | La sélection d'images est produite avec un motif par image, retenue ou écartée, plafond de L25.1 | ✅ §3, `PLAFOND_REFERENCES = 2`, motif obligatoire vérifié par `verifier()` |
| 1 ter | `requete.yaml` relisible et éditable, `valide: false` par défaut, refus sans validation **et** sans référence. Deux tests | ✅ §8 |
| 1 quater | Le temps de la phase 1 est mesuré et comparé à celui de la phase 2 | ✅ §9 |
| 1 quinquies | Les trois formes du champ texte mesurées, verdict publié avec son dénominateur, « +30 % » jamais recopié comme un fait | ✅ §5 — et le dénominateur est **petit**, ce qui est dit |
| 1 sexies bis | L'approche de style retenue est celle que la mesure désigne ; `references` / `ancrages_style` distincts dans `requete.yaml` **et** dans le payload | ✅ §4, et la distinction va jusqu'au texte du prompt (désignation séparée) |
| 1 sexies | Canaux inventoriés, licence vérifiée à la source, coût VRAM mesuré, **un** canal au plus livré, les autres documentés | ⚠ **partiellement** : licences ✅ vérifiées, canaux ✅ inventoriés sur le serveur réel, **aucun** livré, et le **coût VRAM n'a pas pu être mesuré** — §7 dit pourquoi et publie la marge à la place |
| 1 septies | Un test vérifie que `requete.yaml` relu et le payload archivé décrivent la même requête | ✅ `test_le_yaml_relu_et_le_payload_archive_decrivent_la_meme_requete` |
| 2 | Le style traité par l'approche 1, 2, ou explicitement pas traité, avec le tableau sur 10 images | ⚠ **traité par l'approche 1, sur 3 images et non 10** — §4.2. L'approche 2 est livrée désarmée, avec le tableau qui le décide |
| 3 | `construire` est **pur** et testé sans LLM ni moteur | ✅ 32 tests, aucun réseau |
| 4 | Un test prouve qu'un attribut absent de `bible.yaml` ne peut pas entrer | ✅ `test_un_attribut_ABSENT_de_la_bible_ne_peut_pas_entrer` — et §11 dit ce que la garantie ne couvre pas |
| 5 | Le prompt négatif est dans le gabarit, chaque terme avec son motif | ✅ 7 termes, 7 motifs, un test exige que chacun dépasse 40 caractères |
| 6 | `--rejouer` reproduit l'image, ou l'écart est mesuré et publié | ✅ **octet pour octet identique** — voir §9.2 ; et quatre exécutions indépendantes de la même requête donnent la même mesure au centième |
| 7 | Français contre anglais mesuré sur 10 images | ⚠ **mesuré sur 2 images, et sur un HYBRIDE** — §6 |
| 8 | Les fichiers de prompt sont nommés au CHANGELOG, licence en fin de fichier, hors `PROMPTS_REQUIS` | ✅ 4 fichiers, deux tests |
| 9 | `ruff check .` passe ; `pytest -m "not modeles and not lent"` passe sans poids | ✅ |
| 10 | Ce document reprend les critères un par un et dit ce que la mesure ne dit pas | ✅ §11 |

---

## 11. Ce que cette mesure ne dit PAS

1. **Elle ne dit rien de la ressemblance.** Le juge du lot 25 ne sépare « même personnage » de
   « personnages différents de la même œuvre » que **68 fois sur 100** pour un seuil de 80.
   Toutes les colonnes de ressemblance de ce document sont marquées **non opposable**, et le
   protocole humain en aveugle du `PLAN-25` étape 0.3 **n'a toujours pas été exécuté**.
2. **Les dénominateurs sont petits.** Le plan demande 8 personnages et 10 images par axe ; les
   axes qui génèrent ont tourné sur **un personnage** — le seul du corpus à porter plus d'une
   référence validée — et **2 à 3 images par axe**. Un écart de 0,01 sur un descripteur ne se
   lit pas sur trois images.
3. **Le filtre de pureté est franchissable.** Il protège la clause de scène par un vocabulaire
   fermé, apparié à la frontière de mot ; une périphrase — « une chevelure de blé mûr » évitée
   en « des boucles de blé mûr » — passe. Ce qui n'est **pas** franchissable, c'est la
   charpente : aucun chemin de code ne transforme une chaîne de modèle en fragment d'attribut.
   Un test documente la limite plutôt que de célébrer la garantie.
4. **L'apport de la clause de scène n'est pas mesuré.** `illustration/scene.py` est livré
   complet et testé, et le run de bout en bout en a produit deux — bonnes, et vérifiables au
   §9. Aucune image ne les porte : les deux personnages concernés n'ont pas de référence
   validée, et la phase 2 refuse de produire sans référence.
4 bis. **Le comptage des appels de la phase 1 était faux au moment du relevé** — il ignorait
   les appels de texte. Le correctif est livré ; le chiffre publié est celui du run, avec sa
   correction écrite à côté plutôt qu'appliquée en silence (§9.3).
5. **Le défaut du classifieur de couvertures n'est pas corrigé, il est contourné.**
   `core/illustrations.py` manque au moins trois pages typographiées sur ce corpus. Ce lot les
   fait écarter par un modèle de vision ; il ne répare pas le classifieur, et un utilisateur
   qui n'arme pas le modèle garde le défaut entier.
6. **Le seuil qui traduit un descripteur en mot n'est pas mesuré.** Il est posé en tiers de
   l'échelle et écrit pour être contesté.
7. **La reproductibilité mesurée vaut pour CETTE pile.** ComfyUI 0.34.2, ROCm 7.14, RX 7900
   XT, graine fixe, graphe d'édition. Le lot 24 écrivait « la plupart des backends de diffusion
   ne sont pas déterministes » : ils le sont ici, ce qui ne dit rien d'ailleurs.
8. **Rien de ceci ne se généralise à une autre œuvre.** Un tome en couleur, un tome sans
   illustration intérieure, un tome dont les références sont des recadrages de personnage :
   aucun n'a été mesuré, et le mécanisme mesuré ici — « le conditionnement suit le registre
   des références » — prédit que les résultats y seraient différents.
