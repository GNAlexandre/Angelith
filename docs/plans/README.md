# Plans 17 à 22 — destinés à Claude Code

Établis le 2026-08-26, sur la branche `2.0.0`, à partir du dépôt en **2.6.0**.

**Commencez par [`00-CONTEXTE-AGENT.md`](00-CONTEXTE-AGENT.md).** Il porte ce qu'aucun plan ne
répète : conventions du dépôt, règle de numérotation, convention de commit avec disclosure IA,
commandes de test et de mesure, les sept interdits, et la définition de « terminé » en huit
points. Un plan lu sans lui produira du code qui ne passe pas la relecture.

## Comment lancer une session

```
Lis docs/plans/00-CONTEXTE-AGENT.md puis docs/plans/PLAN-NN-….md.
Exécute l'étape 0, publie sa mesure, et arrête-toi pour que je la relise
avant d'écrire une ligne de code.
```

**Un plan = une session = une branche = un `[X.Y.Z]`.** Jamais deux plans dans la même session :
ils se mesurent séparément, donc ils se livrent séparément.

## Les six plans

| Plan | Objet | Nature | Jours |
|---|---|---|---|
| [17](PLAN-17-LE-TRADUCTEUR-CESSE-DE-TRAVAILLER-A-L-AVEUGLE.md) | Structure de planche, type de bulle, locuteur par la queue, vision ciblée, perte de contenu, registre vérifié, relecteur | MINEUR | 16 |
| [18](PLAN-18-LA-COQUILLE-APPLICATIVE.md) | L'interface cesse d'exiger la ligne de commande : créer un projet, importer, glisser-déposer, cinq menus, persistance | MINEUR | 12 |
| [19](PLAN-19-LE-SYSTEME-VISUEL.md) | Le design : tokens, deux thèmes, `Fusion`, typographie en points, douze icônes, états, accessibilité | MINEUR | 10 |
| [20](PLAN-20-L-ATELIER-GITHUB.md) | Automatiser ce qui se vérifie : disclosure IA, Linux débloqué, cohérence des chiffres, garde-fous de fuite, releases | CORRECTIF + MINEUR | 8 |
| [21](PLAN-21-LIRE-L-ONOMATOPEE-AVANT-DE-PRETENDRE-L-ECRIRE.md) | Lire le texte hors bulle pour de vrai, borner l'aire, mesurer le style, valider la traduction | MINEUR | 10 |
| [22](PLAN-22-EFFACER-ET-REDESSINER.md) | Effacer et redessiner : la décision d'architecture, l'effacement, la rotation, le calque PSD | MINEUR ou MAJEUR | 18 |

**Total : 74 jours.** Ce n'est pas un programme à exécuter d'un bloc.

## Ordre d'exécution recommandé

1. **20** — huit jours, aucune dépendance, et chaque garde-fou ajouté remplace une vérification
   que quelqu'un oubliera. Son étape L20.2 (un test qui échoue si la fixture de police est
   sautée) protège les cinq autres plans.
2. **18** puis **19** — dans cet ordre. Styler une interface dont il manque la moitié des actions
   revient à peindre une pièce sans porte. Les deux peuvent avancer en parallèle sur deux
   branches si vous préférez.
3. **17** — après le **lot 15** (externalisation des prompts), qu'il consomme comme prérequis.
4. **21** puis **22**, jamais l'inverse. Effacer une onomatopée à partir d'une lecture fausse
   remplace un défaut signalé par un défaut dessiné.

Le **lot 16** (évaluer les deux poids Apache-2.0 entraînés sur du webtoon) est indépendant et
peut se glisser n'importe où. `docs/mesures/webtoon-2026-08-26.md` a établi que sa condition d'ouverture
est remplie.

⚠ **Son étape zéro a été exécutée en 2.8.0** et elle change la lecture du `PLAN-21` :
`docs/mesures/detecteurs-candidats-2026-08-26.md` montre que `ogkalu/comic-speech-bubble-detector-yolov8m`
(Apache-2.0) n'est pas un détecteur de bulles mais un détecteur de **texte** — il trouve
22 régions de texte de récit hors bulle là où le pipeline ne voit rien, sur un échantillon de
12 planches. C'est donc un candidat sérieux pour remplacer `comic-text-detector` (GPL-3.0 +
Manga109-s), à mesurer avec `ogkalu/comic-text-segmenter-yolov8m`.

## Ce qui restait à faire des plans 10 à 16

Le dépôt a livré **2.1.0** à **2.6.0** : le banc de mesure, le rebranchement de sept mécanismes
inertes, la passe hors bulle activée, les planches muettes de 188 à 153, 33 doubles suspects
attrapés, et le webtoon mesuré de bout en bout. Restaient :

- **lot 15** — externaliser les **seize** instructions codées en dur en Python, que
  `docs/mesures/inventaire-couplage-fr.md` §5 liste site par site. Déjà planifié, non repris ici.
- **lot 16** — évaluer les deux poids Apache-2.0 avant tout affinage. Déjà planifié, non repris.
- **L4.1** (aire minimale de bulle) et **`fenetre_encre_min`** sont livrés **désarmés**, en
  attente de calibration au banc. Ce ne sont pas des oublis : la mesure ne soutenait pas de les
  armer, et c'est écrit.
- **L6.2** (masques locaux avec leur boîte) a été **refusé sur mesure** : le pic réel est de
  270 Mo sur 1,7 Go, pas 865 Mo comme l'affirmait le plan, et « ce qui manque pour le décider
  n'est pas un argument de plus, c'est une planche qui fasse effectivement déborder la mémoire ».
- **Le sous-comptage du webtoon** — 5,9 bulles par bande là où ~25-35 seraient attendues — reste
  entier, et désigne le détecteur. C'est le lot 16.

⚠ **Et un orphelin, que ces plans réparent.** L'ancien PLAN-07 — la qualité de traduction — n'a
jamais été rattaché à un lot de la série 10-16. Le lot 11 en a rebranché les tuyaux (2.2.0) et le
dit lui-même : « ce lot ne gagne aucune bulle, il rend au traducteur le contexte qu'on avait déjà
décidé de lui donner ». Ce que le traducteur reçoit n'a jamais changé. C'est `PLAN-17`, et c'est
le plus gros levier de qualité qui reste.

## Sur la fiabilité de ces plans

Chaque diagnostic est adossé au code de la branche `2.0.0` et aux documents de mesure publiés
par les lots 10 à 14. Les plans ont été relus contre le code par une seconde passe indépendante,
qui a corrigé quinze écarts — dont un bloquant et deux qui inversaient un raisonnement. Les
voici, parce qu'ils sont instructifs :

- **le compte de tests a trois dénominateurs légitimes**, et un plan les avait confondus :
  **2 262** (total), **2 206** (boucle courte), **2 007 / 1 879** (l'effet de PySide6 mesuré par
  `ci.yml`, d'où les 128 tests d'interface). `PLAN-20` L20.3 demande maintenant de vérifier que
  chaque emplacement cite le bon **avec son étiquette**, pas de les unifier de force ;
- **les hallucinations latines de `manga-ocr` sont produites sur une source JAPONAISE**, pas
  latine. L'inverser ferait jeter le vrai contenu d'un webtoon anglais — `PLAN-21` porte
  désormais l'avertissement ;
- **le premier lancement n'est pas muet** : le message « aucun projet trouvé » est émis au niveau
  `warn`, donc il déplie le journal et s'affiche 8 s dans la barre d'état. Le constat de
  `PLAN-18` tient — il n'y a rien à cliquer — mais sa mise en scène était fausse ;
- **vingt occurrences de couleur littérale, dix-neuf valeurs, quatre fichiers** — le relevé
  initial en annonçait dix-huit dans cinq fichiers et en avait manqué trois. D'où le critère 1
  de `PLAN-19` : un inventaire à la main ne suffit pas, il faut le test ;
- **« assembler » n'est pas une action orpheline** : elle existe déjà comme bouton de l'onglet
  « Runs ». Quatre actions de la console sont sans équivalent graphique, pas cinq ;
- un « 687 régions de plus de 20 000 px² » et un « 0,60-0,61 » de remplissage circulaient dans
  des documents de planification antérieurs et **ne se retrouvent nulle part dans le code**. La
  source réelle dit 797 bulles, médiane 0,89, vrais doubles entre 0,72 et 0,91.

Deux faits ont été vérifiés en ligne le 2026-08-26 et sont sourcés dans `PLAN-22` : la licence
Apache-2.0 de Qwen-Image et ses 20 milliards de paramètres, et le fait que **la licence des
poids de LaMa n'a pas pu être établie** — à vérifier sur la source primaire avant tout usage.

## Ce que ces plans demandent de trancher plutôt que d'absorber

- **283 filigranes annoncés contre 92 zones de mobilier attrapées**, sur le même dénominateur de
  448 zones. Le dépôt ne réconcilie pas les deux (`PLAN-21` critère 4).
- Une docstring affirme que la glose est dessinée par `typeset.py` ; **le mot n'y apparaît pas**,
  c'est `manga/rendu.py` qui la dessine (`PLAN-22` L22.5).
