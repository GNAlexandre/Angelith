# Mesures et comptes rendus de lot

Tout ce que le projet a **mesuré**, daté, avec son commit et l'empreinte de sa configuration.
Un fichier par lot livré, plus quelques relevés qui n'appartiennent à aucun lot.

> **La règle qui régit ce dossier**, posée par [`../chiffres-de-reference.md`](../chiffres-de-reference.md) :
>
> **Tout chiffre de communication du projet porte sa source et son dénominateur. Un chiffre
> sans dénominateur n'est pas une mesure, c'est une impression.**
>
> Et son corollaire : **« un tableau qui ne confirme jamais que le plan n'est pas une
> mesure. »** Chaque document ci-dessous reprend les critères de son plan **un par un**, y
> compris ceux qui ne sont pas tenus, et publie une section « ce que la mesure ne dit pas ».

---

## Comptes rendus de lot, du plus récent au plus ancien

> ⚠ **Ce tableau est INCOMPLET au 2026-09-05** : les lots **31 à 34** ont livré leurs documents (`coquille-2026-09-04.md`, `progression-2026-09-05.md`, `lanceurs-2026-09-05.md`, `bibliotheque-2026-09-05.md`) sans que cet index les reçoive. Ils sont dans le dossier, ils ne sont pas dans la liste. La ligne est écrite plutôt que les quatre entrées manquantes parce que résumer le lot d'un autre depuis son seul document, c'est écrire un résumé que personne n'a relu.

| Document | Lot | Ce qu'il établit |
|---|---|---|
| [retouche-2026-09-05.md](retouche-2026-09-05.md) | 35 | **La retouche devient une destination.** ⚠ **Trois prémisses du plan étaient fausses**, et la plus coûteuse tenait dans le dépôt depuis la 1.5.0 : `gui/cache_apercu.py` annonçait « la fenêtre ±10 pèse ~21 Mo ; le plafond (120 Mo) la contient largement ». Mesuré : **9,35 Mo par aperçu** sur un tome paginé et **35,2 Mo** sur une bande, soit ~196 Mo pour 21 planches — le cache évinçait ce que la voie de lecture venait de composer et le recomposait, **137 fois pour 12 aperçus gardés en 120 s, indéfiniment, sur un panneau que personne ne touchait**. Après : 13 pour 12. La bande webtoon n'est pas « 1 bande / chapitre » mais **neuf**, si bien que la question de la « seule unité à précharger » **n'a aucun cas au corpus**. Le trou de garde annoncé par le lot 31 **ne s'ouvre pas** : les six chemins de perte sont nommés, trois n'ouvrent aucune boîte, et c'est le résultat — « un dialogue qui se pose à chaque changement d'onglet est un dialogue qu'on apprend à cliquer sans lire ». **Douze critères sur douze tenus, deux autrement que le plan l'imaginait** (la navigation par segment est un « non » documenté, ce que le plan autorisait) |
| [identite-2026-08-29.md](identite-2026-08-29.md) | 25 | L'identité, la nouveauté et le style. **Deux verdicts opposés** : le conditionnement par référence RÈGLE le registre graphique que le lot 24 avait manqué (trait et noir et blanc au lieu de photo couleur) — et le juge automatique **ne sépare pas** l'identité : 0,68 de séparation entre « même personnage » et « personnages différents de la même œuvre », contre 0,91 entre deux œuvres. Le garde-fou est livré, ses verdicts marqués **non opposables**, et le protocole en aveugle **n'a pas été exécuté** |
| [prompt-illustration-2026-08-30.md](prompt-illustration-2026-08-30.md) | 26 | **Le prompt vient de l'œuvre — et ce n'est pas sa FORME qui décide, c'est le CHOIX des images.** Le matériau est là (14 fragments cités sur 15 pour 3 personnages ; le genre passe de **0/11 à 9/11** en lisant le glossaire). Le modèle de VISION lit ce que le classifieur du lot 23 ne voit pas — il désigne « couverture avec titre » sur des pages rangées en `pleine_page`, dont l'*Afterword* : **4 motifs vérifiés à l'œil sur 4 sont exacts**. Conséquence, une seule variable changée : le **régime de couleur** bascule enfin du bon côté, ce que le lot 25 déclarait insoluble. Le revers est publié : armé, ce choix fait passer le corpus de **4 personnages illustrables à 1**, et il est donc livré DÉSARMÉ |
| [atelier-2026-08-31.md](atelier-2026-08-31.md) | — | **Une commande, une œuvre entière, et trois défauts que seul l'usage pouvait montrer.** Éprouvé sur une œuvre de 4 tomes et **80 illustrations exploitables** — cinq fois le corpus précédent. Une référence sans son tome était **ambiguë** (deux volumes, un même `image1`) ; le classifieur manquait les couvertures **republiées** (seuil de sosie posé dans un vide mesuré, 0,594 → 0,797) ; et une revue en bloc ne vaut rien — sur le premier personnage relu, **3 attributs proposés sur 5 étaient faux**. Résultat qui tient en une image : les trois faux rejetés, et l'image produite a quand même les bons cheveux — ce sont les RÉFÉRENCES qui portent l'identité |
| [atelier-illustration-2026-09-02.md](atelier-illustration-2026-09-02.md) | 27 | **L'atelier dans l'interface, et la porte que les deux interfaces franchissent.** Le chiffre de l'étape 0.1 n'a pas eu besoin d'être remesuré : les trois relevés des lots 24-26 donnent une médiane pondérée de **103,7 s/image**, soit **1,7× le seuil du haut** du tableau du plan → « run par lot ». **Une prémisse du plan est fausse** : la bascule de modèle n'est PAS le poste dominant — 2,03 s contre 103,7 s, soit 2 %. Le critère 4 est **livré plus étroit que le plan** : le LLM ne revient que si la carte est réellement libre, sinon on le DIT. Et un défaut du dépôt trouvé en chemin : le `config.yaml` **publié** armait la brique depuis la 2.20.0, six valeurs entrées par mégarde dans un lot qui parlait de polices |
| [canaux-2026-09-03.md](canaux-2026-09-03.md) | 30 | **Les canaux qui manquent.** ⚠ **AUCUN CANAL N'EST LIVRÉ, et c'est la conclusion.** Le plan exigeait de choisir un canal sur son **apport mesuré** ; l'apport dépend du juge du lot 29, qui n'a pas livré — même sur le PC principal, le critère 1 n'aurait pas pu être tenu. Le canal instrumenté a donc été choisi sur la **dette d'installation**, et c'est écrit comme tel : nœuds intégrés à ComfyUI contre nœud tiers pour EliGen. Livré : un graphe **candidat** que le validateur connaît sans passer en rouge, `CanalExige` pour le premier graphe du dépôt qui **ne dégrade pas**, une sixième vérification qui tranche la copie non marquée — ⚠ **le conseil `SaveImageWebsocket` du dépôt était FAUX**, ce client ne sait pas lire ce nœud —, et le protocole compté de `/free` (20 appels, en sondant entre chaque : le serveur MEURT, il ne rend pas d'erreur). Un défaut silencieux corrigé : `%image_controle%` n'était pas un marqueur élagable. **Quatre critères sur neuf tenus, deux à moitié, trois non tenus** |
| [identite-2026-09-03.md](identite-2026-09-03.md) | 29 | **Le juge et le corpus.** Le protocole en aveugle est enfin OUTILLÉ — seuil fixé à la création et relu de là, étiquettes absentes du nom des fichiers **et de leur date**, réponses horodatées en ajout seul — et le corpus se compte (0/1/2/≥3, avec et sans les couvertures). ⚠ **Sept critères sur neuf ne sont pas tenus**, et trois ressources manquaient, pas une : ni bible (0 fichier sur 17 projets), ni poids d'encodeur, ni carte. ⚠ Le plan avait une étape exécutable **sans GPU** que personne n'avait vue. Deux défauts silencieux corrigés : le champ de recadrage écrit sous un nom et lu sous un autre depuis six versions, et `--balayage` qui levait un `AttributeError` depuis la 2.18.0. Un résultat négatif mesuré sur **402 images** : la boîte d'encre retire les marges, pas la page |
| [comfy-visible-2026-09-02.md](comfy-visible-2026-09-02.md) | 28 | **Voir ce que le projet envoie à ComfyUI.** Une sonde, un validateur à cinq contrôles qui refuse **avant** le GPU, le graphe réellement envoyé archivé à côté de chaque image. ⚠ **Trois critères sur neuf ne sont pas tenus, et c'est la MACHINE** : la session a tourné sur le PC secondaire — pas de ComfyUI, pas de carte. Deux résultats qui contredisent le plan : la vérification des modèles ne peut PAS se faire sur une liste de champs écrite à la main (elle aurait raté `ModelPatchLoader.name`), et le seuil de VRAM appliqué à la lettre aurait crié à chaque seconde génération. Et un relevé : **7 affirmations d'état dans le code, 1 périmée depuis six versions** |
| [connecteur-qwen-2026-08-29.md](connecteur-qwen-2026-08-29.md) | 24 (suite) | Le connecteur Qwen-Image **mesuré sur la 7900XT**. Les trois mesures que le lot 24 n'avait pas pu faire sont faites : 103,7 s/image à 4 pas et 629,8 s à 50, pic **14 421 Mio sur 20 464**, **0 échec sur 25 générations**, rejeu **bit-à-bit identique**. Et **six défauts** que 110 tests verts n'avaient pas vus. Résultat négatif mesuré : les images sont **hors du registre graphique** du tome (écart 0,200, régime de couleur opposé) |
| [socle-generatif-2026-08-29.md](socle-generatif-2026-08-29.md) | 24 | Le socle génératif. **Trois des quatre mesures du plan n'ont pas pu être faites** — ni GPU ni réseau — et la non-mesure est écrite dans le comportement du logiciel : moteur `factice` par défaut, état `experimental`, aucune URL de poids codée en dur. La frontière, elle, est mesurée : un run complet laisse **toutes** les empreintes SHA-256 préexistantes inchangées |
| [bible-visuelle-2026-08-29.md](bible-visuelle-2026-08-29.md) | 23 | La bible visuelle. 446 illustrations classées, 317 exploitables (71,1 %). Trois résultats négatifs : un critère du plan retiré, un critère hors d'atteinte (plafond 15 au lieu de 30), la sonde vision dans la zone grise |
| [relettrage-2026-08-28.md](relettrage-2026-08-28.md) | 22 | Effacer et redessiner. **Le principe « l'IA ne dessine jamais » est confirmé, pas renégocié.** L'effacement livré est déterministe — et n'efface aujourd'hui aucune zone, faute de lecture concordante |
| [sfx-2026-08-28.md](sfx-2026-08-28.md) | 21 | Lire l'onomatopée avant de prétendre l'écrire. `manga-ocr` est exact **6 fois sur 41** (14,6 %) sur le texte hors bulle. C'est ce chiffre qui tient `manga.onomatopees.mode` à `"rapport"` · échantillon brut : [sfx-echantillon-2026-08-28.json](sfx-echantillon-2026-08-28.json) |
| [atelier-github-2026-08-28.md](atelier-github-2026-08-28.md) | 20 | L'atelier GitHub : ce qui se vérifiait à la main, et ce qui se vérifie maintenant |
| [systeme-visuel-2026-08-27.md](systeme-visuel-2026-08-27.md) | 19 | Le système visuel de l'interface graphique, avec ses captures avant/après |
| [coquille-applicative-2026-08-27.md](coquille-applicative-2026-08-27.md) | 18 | La coquille applicative |
| [webtoon-2026-08-26.md](webtoon-2026-08-26.md) | — | Le webtoon de bout en bout. **Nomme quatre affirmations du dépôt lui-même qui étaient fausses**, et livre trois réglages désarmés parce que la mesure ne soutenait pas de les armer |
| [detecteurs-candidats-2026-08-26.md](detecteurs-candidats-2026-08-26.md) | 16, L9.0 | Les deux poids Apache-2.0 candidats. Aucun ne remplace le détecteur ; celui qui récupère 52 des 188 planches muettes **ne détecte pas des ballons** |
| [doubles-2026-08-25.md](doubles-2026-08-25.md) | — | Bulles doubles et texte hors bulle : la scission |
| [escalade-2026-08-25.md](escalade-2026-08-25.md) | — | L'escalade de détection. Le premier document du dépôt à publier **ce que la mesure ne dit pas** |
| [banc-2026-08-25.md](banc-2026-08-25.md) | — | Le tableau du banc à cette date — la ligne de base à laquelle les suivants se comparent |

## Relevés et engagements, hors lot

| Document | Ce que c'est |
|---|---|
| [seuils-affinage-detecteur.md](seuils-affinage-detecteur.md) | **Un engagement, pas un rapport.** Les quatre seuils qui autoriseraient — ou interdiraient — un affinage du détecteur, écrits **avant** la première époque. Des seuils posés après coup sont des seuils qu'on ajuste jusqu'à ce qu'ils passent |
| [inventaire-couplage-fr.md](inventaire-couplage-fr.md) | L'état des lieux du couplage au français, site par site, avec chemin et ligne. Livrable L1 du plan « langue cible dynamique » |
| [sonar-2026-08-26.md](sonar-2026-08-26.md) | Le brief de mise aux normes SonarQube Cloud |

---

## Écrire le prochain

Un lot ne se termine pas sans son document, et il porte **la date, le commit et l'empreinte
SHA-256 de `config.yaml`** — ce que `tools/banc.py --markdown` produit déjà.

```powershell
python tools/banc.py --tous --markdown  > docs/mesures/banc-<AAAA-MM-JJ>.md
python tools/bible.py --tous --rapport --markdown > docs/mesures/bible-visuelle-<AAAA-MM-JJ>.md
```

⚠ **Le nom d'un banc porte sa date** : `docs/mesures/banc-AAAA-MM-JJ.md`. Deux tableaux ne se
comparent que si l'on sait lequel est le plus récent, et `tools/verifier_livraison.py` refuse
un banc sans date dans son nom.

Le protocole — quelles métriques, sur quel corpus, sous quelles licences — est dans
[`../procedures/banc-de-mesure.md`](../procedures/banc-de-mesure.md), qui n'est **pas** une
mesure : il décrit une méthode, il ne se périme pas, et lui coller une date le ferait paraître
obsolète à chaque run.

Les plans dont ces documents sont les comptes rendus vivent dans [`../plans/`](../plans/README.md).
