# L'atelier GitHub — ce qui se vérifiait à la main, et ce qui se vérifie maintenant

- **Date de mesure** : 2026-08-28
- **Commit de base** : `51ad6e1`
- **Version livrée** : 2.11.0
- **Lot** : 20 (`docs/plans/PLAN-20-L-ATELIER-GITHUB.md`)
- **Protocole** : toutes les mesures ci-dessous se reproduisent par une commande, écrite à côté

> **Ce que ce document n'est pas.** Ce n'est pas un compte rendu de ce qui a été ajouté — le
> CHANGELOG le fait. C'est le relevé de **ce que les garde-fous ont trouvé le jour où ils ont
> été branchés**, y compris ce qui est gênant, et la reprise des dix critères du plan **un par
> un**, y compris les trois qui ne sont pas pleinement tenus.

---

## Étape 0 — Le tableau des vérifications manuelles

Le plan demandait de lister chaque vérification qu'un humain fait aujourd'hui, son coût
d'oubli, et de décider ce qui s'automatise. Le voici, complété : la colonne « statut » est ce
que ce lot a réellement livré.

| Vérification | Coût d'un oubli | Statut à l'issue du lot |
|---|---|---|
| `core/version.py` correspond à la première entrée datée du CHANGELOG | tag non documenté | **déjà automatisé** — `tests/test_version.py`, et il tourne bien en CI (vérifié : il est dans la boucle courte) |
| le tag posé correspond à `core/version.py` | release dont le contenu n'est documenté nulle part | **automatisé** — `tools/notes_de_version.py --verifier`, appelé par le workflow `Publication` |
| le commit porte la disclosure IA de `CONTRIBUTING.md` | historique non conforme à la politique de financement, **irréparable rétroactivement** | **automatisé, non bloquant jusqu'au 2026-10-01** — taux mesuré : **7/105** |
| un commit non relu n'est pas fusionné | contribution que personne ne peut défendre | **automatisé et bloquant** — job `relecture`, distinct du précédent |
| un chiffre de communication porte sa source et son dénominateur | la règle de `docs/chiffres-de-reference.md` violée en silence | **partiellement automatisé** — les quatre invariants exacts sont testés ; la règle générale reste humaine, elle n'est pas décidable |
| le compte de tests est le même dans les trois fichiers qui le citent | quatre chiffres pour un objet, ce qui est **déjà arrivé** | **automatisé** — `tests/test_coherence_chiffres.py` |
| `PUBLICATION-ANGELITH.md` ne part pas vers le miroir public | une fuite — un commit existe déjà pour ça (`221a902`) | **automatisé** — `tools/verifier_arbre.py --index`, appelé par la procédure |
| aucun titre d'œuvre en clair dans un fichier suivi | annule tout le raisonnement juridique de la purge | **automatisé sur le DIFF ; l'arbre existant en porte 19, mesurés ci-dessous** |
| aucune œuvre commerciale sous `sources/` ou `build/` | la purge du corpus (`86c3d3d`, `b3d1eaa`) défaite | **automatisé** — job `arbre`, bloquant |
| les poids ONNX ne sont pas commités | 104 Mo + 94,7 Mo dans l'historique, **définitivement** | **automatisé** — même job |
| le lot publie son tableau daté | la règle de `docs/roadmap.md` non tenue | **automatisé pour la FORME** (nom daté, date/commit/empreinte présents) ; l'existence du tableau reste humaine |
| une entrée de CHANGELOG accompagne un changement de produit | lot livré tard le soir, entrée oubliée | **automatisé** — job `livraison`, échappatoire nommée `sans-changelog` |
| une réécriture de prompt nomme son fichier dans le CHANGELOG | `git checkout <tag> -- langues/` ne dit plus quelle voix rejouer | **automatisé** — même job |
| les deux OS voient la même suite de tests | couverture perdue en silence, CI verte | **automatisé** — job `collecte`, bloquant |
| une police japonaise est disponible pour la planche synthétique | **toute** la couverture détection/OCR/orchestrateur sautée sans un mot | **automatisé** — `tests/test_fixture_police.py`, qui échoue au lieu de sauter |
| le banc n'a pas régressé après une mise à jour amont | régression découverte au prochain run manuel | **automatisé** — run hebdomadaire (`schedule`) avec `pip install --upgrade onnxruntime numpy` |
| les licences de modèles concordent entre les trois documents qui les citent | une licence fausse décide de ce qu'on a le droit de redistribuer | **automatisé** — `tests/test_coherence_chiffres.py` |
| aucun binaire d'œuvre versionné par accident | fuite | **laissé à l'humain** — la liste des extensions légitimes (`templates/reference*.docx`, `docs/img/*`) demande un jugement, pas un motif |
| le niveau MAJEUR/MINEUR/CORRECTIF est le bon | numérotation qui ne veut plus rien dire | **non décidable** — il se décide d'après ce que le lot fait à l'utilisateur |

---

## 1. La disclosure IA — le taux, avant de rendre quoi que ce soit bloquant

```powershell
python tools/verifier_disclosure.py --historique 107
```

| Mesure | Valeur |
|---|---|
| commits dans l'historique | **107** |
| exemptés (fusions, robots) | **2** |
| jugés | **105** |
| **conformes** | **7** — soit **7 %** |
| conformes mais non fusionnables (`Revu … : non`) | **2** |

**Ce que ce chiffre veut dire, et ce qu'il ne veut pas dire.** Il ne dit pas que 98 commits ont
été écrits par un modèle sans le déclarer : l'immense majorité est antérieure à l'adoption de
la convention, qui date du 2026-08-21 (`86c3d3d`). Il dit une chose plus simple et plus utile :
**la convention existe depuis une semaine et n'est appliquée qu'à cinq commits sur les vingt
qui l'ont suivie.** Un historique de douze mois ne se documente pas rétroactivement ; ce qui se
décide, c'est la suite.

**Trois précautions du plan, toutes tenues, et une quatrième trouvée en route.**

1. **`Assisté par : aucun` est accepté.** Une correction de coquille écrite à la main n'a pas
   de prompt. Ce qui est refusé, c'est l'ABSENCE de ligne — elle ne distingue pas
   « écrit à la main » de « oublié ».
2. **Livré non bloquant, avec sa date de bascule : le 2026-10-01.** Elle est écrite dans
   `.github/workflows/garde-fous.yml` et dans `CONTRIBUTING.md`, pas seulement ici. Un
   garde-fou qui casse tous les builds le jour de sa livraison est désarmé le lendemain.
3. **`Revu … : non` passe le job et bloque la fusion.** Deux jobs, deux drapeaux
   (`--bloquant`, `--exiger-relecture`), et le second est bloquant dès maintenant : il ne juge
   pas un format qui n'existait pas hier, il juge ce que l'auteur de la PR vient d'écrire.
4. ⚠ **Les commits de robots sont exemptés, et ce lot en crée.** Dependabot, mis en place par
   ce même lot, produira des commits sans prompt ni modèle. Sans exemption, chaque PR de
   dépendance deviendrait rouge le 2026-10-01 — c'est-à-dire au moment où plus personne ne se
   souviendrait pourquoi. L'exemption est nommée maintenant plutôt que découverte alors.

**Un cas réel que le garde-fou attrape, et qui vaut d'être cité.** Le commit `3ef803b`
(lot 16) écrit `Revu et testé manuellement : linter et tests automatiques passés`. Ce n'est ni
`oui` ni `non` : c'est une phrase, et une phrase ne se compte pas. Le contrôle la refuse — non
pour la punir, mais parce qu'un verdict illisible ne permet ni de savoir si un humain a relu,
ni de bloquer la fusion s'il ne l'a pas fait.

---

## 2. Le garde-fou d'arbre — et ce qu'il trouve dans l'arbre existant

```powershell
python tools/verifier_arbre.py --suivi --non-bloquant
```

**19 infractions sur 363 fichiers suivis**, toutes de la règle « fuite » : un titre d'œuvre en
clair dans un fichier versionné, alors que `docs/PUBLICATION-ANGELITH.md` demande depuis le
2026-08-21 que « un commentaire de mesure écrit à partir de maintenant nomme le corpus par sa
désignation neutre — `manga A`, `roman A`… — et jamais par son titre ».

| Fichier | Occurrences |
|---|---|
| `docs/mesures/banc-2026-08-25.md` | 31 |
| `docs/mesures/doubles-2026-08-25.md` | 29 |
| `docs/mesures/escalade-2026-08-25.md` | 15 |
| `docs/mesures/detecteurs-candidats-2026-08-26.md` | 10 |
| `CHANGELOG.md` | 9 |
| `docs/chiffres-de-reference.md` | 7 |
| `config.yaml` | 4 |
| `manga/orchestrator_manga.py` | 4 |
| `manga/bubbles_split.py`, `manga/ocr.py`, `manga/planche.py`, `tests/test_manga_doubles_et_hors_bulle.py`, `docs/mesures/webtoon-2026-08-26.md` | 2 chacun |
| `manga/checkpoints.py`, `manga/detection.py`, `manga/geometry.py`, `tests/test_manga_escalade.py`, `tests/test_glossary_reintegration.py`, `docs/plans/PLAN-23-LA-BIBLE-VISUELLE.md` | 1 chacun |

> ⚠ **Une prémisse du plan était optimiste, et il faut le dire.** Le plan présentait la fuite
> comme un risque à prévenir. **Elle est déjà là** : la vérification de
> `docs/PUBLICATION-ANGELITH.md` — « doit ne RIEN renvoyer » — ne renvoie pas rien aujourd'hui,
> et n'aurait rien renvoyé à aucune des publications passées. Le premier `grep` de la procédure
> est donc, en l'état, une consigne que personne n'a pu suivre.
>
> **Ce que ça change pour la conclusion du document de publication.** Il affirme
> qu'« Angelith ne peut structurellement pas fuiter, parce qu'il n'y a plus rien à fuiter dans
> l'arbre ». C'est vrai des **chemins de fichiers** (`sources/<Titre>/`), qui étaient le risque
> principal et qui sont bien purgés. **Ce n'est pas vrai des commentaires de mesure** : 19
> fichiers en portent, dont quatre modules de `manga/` et deux fichiers de tests. La purge a
> traité l'arborescence ; elle n'a pas traité la prose.

**Conséquence sur la conception du garde-fou, et c'est la décision la plus importante du
lot.** Juger le contenu ENTIER des fichiers modifiés rendrait rouge toute PR qui touche l'un de
ces 19 fichiers — c'est-à-dire à peu près toute PR de la brique manga. Le garde-fou serait
retiré dans la semaine, et la protection serait alors nulle au lieu d'être partielle. Il juge
donc :

- **les lignes AJOUTÉES** par la PR, en bloquant. La fuite neuve est refusée, et celui qui
  ouvre la PR contrôle ce qu'il ajoute.
- **l'arbre entier**, en mesurant, publié dans le résumé de chaque PR. La dette héritée ne
  colore rien en rouge, mais elle ne disparaît pas de la vue.

**Le garde-fou a déjà tiré sur du travail récent.** Sur `HEAD~1...HEAD` (le commit `51ad6e1`,
« Push Plan Brique Generation Image »), il refuse `docs/plans/PLAN-23-LA-BIBLE-VISUELLE.md` :
un titre y a été **ajouté** hier. Ce n'est pas une infraction théorique de plus, c'est la
démonstration que la règle du 21 août n'était pas tenue faute d'outil pour la tenir.

**Ce qui n'a pas été fait, et pourquoi.** Nettoyer les 19 fichiers n'est pas dans ce lot.
`CHANGELOG.md` et `config.yaml` sont des documents historiques — réécrire une entrée de
changelog datée pour en retirer un mot est une réécriture de l'histoire, pas une correction ;
et `config.yaml` est un document dont chaque valeur est justifiée par un chiffre attaché à un
tome nommé. Le tri demande un jugement, tome par tome. **C'est un lot à part**, et il a
maintenant sa liste exacte.

⚠ **Les titres ne sont repris ni dans ce document, ni dans les messages de l'outil.** Le
journal d'une CI publique est aussi lisible que le fichier qu'il dénonce ; un garde-fou qui
publierait ce qu'il interdit d'écrire serait sa propre fuite. Les motifs vivent dans
`docs/PUBLICATION-ANGELITH.md`, qui est retiré de l'arbre public à l'étape 3 de la procédure —
et l'outil les y lit plutôt que d'en garder une copie.

---

## 3. La police, le skip silencieux, et la matrice d'OS

**C'est l'étape qui justifie le lot à elle seule**, et le plan le disait déjà : le problème
n'était pas la police, c'était le **silence**.

### Avant

```python
_JP_FONT = "C:/Windows/Fonts/msgothic.ttc"
if not Path(_JP_FONT).exists():
    pytest.skip("police japonaise Windows introuvable (msgothic.ttc)")
```

Sur un runner Linux : la fixture `synthetic_manga_page` est sautée, tous les tests qui la
demandent sont sautés, **pytest sort 0**, et le compte-rendu ne porte pas une ligne pour le
dire. La couverture détection / OCR / orchestrateur — le code le plus cher et le plus risqué du
dépôt — disparaît sans trace. C'est pour cela, et pour cela seul, que `ci.yml` était cloué à
`windows-latest`.

### Après, dans l'ordre — et l'ordre est le point

| # | Livré | Effet |
|---|---|---|
| 1 | `tools/polices.py` | la police se résout par `ANGELITH_POLICE_JP`, puis par une liste de candidats par plateforme (3 sous Windows, 5 sous Linux, 3 sous macOS) |
| 2 | `tests/test_fixture_police.py` | **échoue** quand aucune police n'est trouvable, et le message nomme la commande d'installation |
| 3 | matrice `[windows-latest, ubuntu-latest]` + job `collecte` | la CI tourne sur les deux OS et **casse** si les deux ne collectent pas le même nombre de tests |

Le point 2 est écrit avant le point 3 parce qu'il aurait dû l'être depuis le début : il ne
coûte rien sur Windows, et il aurait rendu le problème visible dès qu'il est apparu.

**Le garde-fou est plus fin qu'une simple présence de fichier.** Pillow rend des tofus sans
lever quand la police résolue ne couvre pas les kana : la bulle serait « lettrée » de
rectangles vides, et le détecteur ne verrait pas la même chose. Le second test mesure donc
**l'encre réellement posée à l'intérieur de la bulle** (> 100 pixels sombres, hors trait de
contour). Une police latine résolue par erreur ne passerait pas.

⚠ **Aucune police n'est embarquée dans le dépôt**, et ce n'est pas un oubli : `NOTICE` ne porte
que ce dont le droit de redistribution est établi — `templates/fonts/wildjess normal.ttf` est
hors suivi pour cette raison exacte. On résout une police du système, on ne la distribue pas.

⚠ **Pas de macOS dans la matrice**, alors que `tools/polices.py` en connaît les candidats.
`docs/roadmap.md` le classe hors périmètre faute de machine pour le tester ; une CI verte sur
un OS que personne n'utilise donne une fausse assurance. Les candidats sont là pour un
contributeur, pas pour un badge.

---

## 4. Les chiffres — quatre invariants, et trois dénominateurs qui restent trois

### Le compte de tests, remesuré

```powershell
python tools/compte_de_tests.py
python tools/compte_de_tests.py -m "not lent and not modeles"
```

| Chiffre | Dénominateur | Avant (2026-08-25) | Après (2026-08-28) |
|---|---|---|---|
| total | `--collect-only -q`, toutes dépendances optionnelles | 2 262 | **2 852** |
| boucle courte | `-m "not lent and not modeles"` | 2 206 | **2 795** |
| désélectionnés | `lent`, dont 22 aussi `modeles` | 56 | **57** |
| `def test_` dans `tests/` | plus petit que le total (paramétrisation) | 2 063 | **2 603** |

**71 tests neufs**, tous sans Qt, sans modèle et sans réseau :

| Fichier | Tests | Ce qu'il couvre |
|---|---|---|
| `tests/test_outils_atelier.py` | 51 | les cinq garde-fous, cœur pur, sans dépôt git |
| `tests/test_coherence_chiffres.py` | 10 | la règle des chiffres, là où elle est décidable |
| `tests/test_fixture_police.py` | 10 | la police, l'encre réellement posée, la résolution |

Exécution de la boucle courte au commit du lot : **2 793 passés, 2 sautés, 57 désélectionnés**.
Les deux sautés sont légitimes et nommés : `tests/test_epub.py` demande un `sources/` qui n'est
pas versionné — et ils sautent pour la même raison sur les deux OS, ce qui est précisément ce
que le job `collecte` vérifie.

⚠ **Le troisième dénominateur n'a PAS été remesuré, et il porte sa date.** `ci.yml` écrit
« 2 644 tests contre 2 504, soit 140 » au 2026-08-27 : c'est la mesure de l'**effet de
l'installation de PySide6**, dans la configuration de la CI (socle + GUI + dev, sans
`requirements-manga.txt`). Le lot 20 a changé le total du dépôt, pas le rapport entre « avec »
et « sans » ; le remesurer demande un run dédié sans PySide6, qui n'a pas été fait. Le test
vérifie donc son **arithmétique** (2 644 − 2 504 = 140) et la présence de sa **date** — pas son
égalité avec le total, qui serait fausse.

### Ce que le test vérifie, et ce qu'il refuse de vérifier

`tests/test_coherence_chiffres.py` traite `docs/chiffres-de-reference.md` comme **la source**,
ce qu'il dit déjà être, et vérifie quatre invariants exacts :

1. les trois fichiers de la colonne « Où » citent **ce** nombre **avec cette date** ;
2. l'arithmétique tient : 2 795 + 57 = 2 852 ;
3. tout `docs/banc-*.md` porte une date dans son nom, une date de mesure, un commit et une
   empreinte SHA-256 de `config.yaml` — ce que `tools/banc.py --markdown` produit ;
4. les licences de modèles concordent entre `manga_models/README.md`, `docs/ai-provenance.md`
   et `docs/chiffres-de-reference.md`.

⚠ **Il ne vérifie pas que « tout chiffre porte son dénominateur ».** Ce n'est pas décidable par
une expression régulière, et un garde-fou qui produit des faux positifs sur de la prose est
contourné avant d'avoir servi. La règle générale reste à la relecture humaine — c'est une
limite, elle est écrite, et elle n'est pas près de se lever.

**Preuve que le test mord.** En mettant à jour `docs/chiffres-de-reference.md` seul, la suite
est passée au rouge sur les trois fichiers, avec le message attendu (« README.md ne cite pas le
total de 2852 tests annoncé par docs/chiffres-de-reference.md »). C'est le test qui aurait
échoué avant le lot, sur l'état où 1 908, 1 657 et 2 262 coexistaient.

**Une exception nommée, et la même des deux côtés.** `docs/procedures/banc-de-mesure.md` est le
**protocole** du banc, pas une mesure : il n'a ni date ni commit et ne doit pas en avoir, sans
quoi il paraîtrait périmé à chaque run. `tests/test_coherence_chiffres.py` et
`tools/verifier_livraison.py` portent tous deux l'exception, au même titre et avec la même
raison écrite.

---

## 5. Le banc — ce qu'il publie, et ce qu'il ne mesure pas

Trois ajouts, aucun changement à la mesure elle-même :

1. **Le tableau en résumé de job** (`$GITHUB_STEP_SUMMARY`), précédé de l'avertissement qui
   décide de son honnêteté :

   > ⚠ **Corpus synthétique UNIQUEMENT.** Ce banc ne voit pas les 17 projets réels : ils ne
   > sont pas dans le dépôt et ne peuvent pas y être (œuvres purgées, Manga109-s sous
   > conditions académiques). Le corpus réel se mesure en local par
   > `python tools/banc.py --tous`.

   Un job nommé « banc de détection » qui ne dirait pas cela laisserait croire que le corpus
   réel est couvert.
2. **Un artefact**, conservé 90 jours : comparer deux dates sans avoir gardé un terminal
   ouvert. Le résumé de job, lui, s'efface avec la rétention du run.
3. **Un run hebdomadaire** (lundi 04:17 UTC) qui fait `pip install --upgrade onnxruntime numpy`
   **avant** de mesurer. Rejouer chaque lundi la même mesure sur les mêmes versions ne dirait
   rien de neuf ; ce qu'on cherche est une régression de post-traitement due à une mise à jour
   amont — et `tests/test_banc_corpus_synthetique.py` note lui-même que ce post-traitement
   n'est pas bit-à-bit reproductible d'une version d'onnxruntime à l'autre.

**La commande de l'étape a été exercée en local**, avec les poids en place — c'est la seule
étape de CI de ce lot dont on sache qu'elle produit bien quelque chose :

```
python tools/banc.py --corpus tests/corpus/synthetique --markdown
```

| régime | planches | rappel | précision | F1 | bulles annotées | bulles détectées |
|---|---|---|---|---|---|---|
| **tous** | 3 | 0,82 | 1 | 0,90 | 22 | 18 |
| manga | 2 | 0,79 | 1 | 0,88 | 14 | 11 |
| webtoon | 1 | 0,88 | 1 | 0,93 | 8 | 7 |

⚠ **Ce tableau n'est pas un résultat du lot.** Le lot ne touche ni au détecteur, ni aux seuils,
ni au corpus : ce sont les mêmes chiffres qu'avant, et c'est le but — ce qui change est **où
ils s'affichent**. Ils sont reproduits ici uniquement pour montrer que l'étape de résumé n'est
pas vide.

**Une économie assumée** : le banc est exécuté **une** fois, écrit dans un fichier, puis recopié
dans le résumé et téléversé. `--corpus` charge le détecteur et infère sur chaque planche ; le
lancer deux fois paierait la mesure deux fois pour le même chiffre.

⚠ `if: always()` sur le tableau du banc, contrairement à la couverture. Ce n'est pas une
incohérence : un tableau de banc sur un run rouge est précisément celui qu'on veut lire, c'est
lui qui dit **de combien** le rappel a baissé. Ce qu'on refuse de publier sur run rouge, c'est
un pourcentage de couverture calculé sur une exécution incomplète.

---

## 6. Publier — ce qui est automatisé, et ce qui reste à la main

`tools/notes_de_version.py` découpe la section de CHANGELOG d'un tag et en fait le corps de la
release. Le CHANGELOG fait 380 Ko et ses entrées nomment les fichiers, citent les mesures et
expliquent les arbitrages : **ce sont déjà des notes de version**. En rédiger de secondes
créerait un texte parallèle qui divergerait — le défaut que ce dépôt documente pour les
chiffres, transposé à la prose.

Le garde-fou qui compte est `--verifier` : il refuse un tag qui ne correspond pas à
`core/version.py`. C'est le complément symétrique de `tests/test_version.py` ; à eux deux,
**tag ⇄ version ⇄ CHANGELOG** ne peuvent plus diverger.

### ⚠ La publication vers le miroir n'est PAS automatisée, et c'est un critère non tenu

Le plan demandait d'automatiser `docs/PUBLICATION-ANGELITH.md` pour rendre la liste noire
obligatoire par construction. **Ce n'est pas fait, et ce n'est pas un manque de temps.**

1. Le push exige un jeton d'écriture sur un second dépôt. Ce secret n'existe pas, et livrer un
   workflow qui échouerait à sa première exécution serait livrer une capacité fausse.
2. **La vraie raison** : la procédure repose sur `git read-tree --reset -u`, qui écrase un
   arbre entier. La rendre automatique sur un tag transformerait une erreur de tag en
   publication d'un arbre faux vers un dépôt destiné à devenir public. Ce qui devait être
   automatisé, c'est le **garde-fou** ; l'irréversible ne le devait pas.

**Ce qui est livré à la place**, et qui tient l'intention du plan : les trois `grep` recopiés à
la main d'une publication à l'autre — où un motif oublié dans la recopie ne se voit pas — sont
remplacés par `python tools/verifier_arbre.py --index`, une commande, sur l'index, avant le
commit. Et l'outil **refuse de rendre un verdict vert quand il ne trouve pas ses motifs** : sur
la branche `public`, où `docs/PUBLICATION-ANGELITH.md` n'existe pas, il se déclare aveugle et
sort en erreur plutôt que de passer.

### Dependabot — mensuel, groupé, et étiqueté

Une PR par mois, groupée, sur `pip` et sur `github-actions`. **Pas d'hebdomadaire** : sur un
projet à un mainteneur, un flux continu de PR de dépendances devient du bruit qu'on cesse de
lire, et c'est exactement comme cela qu'une mise à jour cassante passe au milieu de neuf mises
à jour anodines. L'étiquette `sans-changelog` est posée d'office — une montée de version ne
change rien à ce qu'un tome produit — et c'est celle que `tools/verifier_livraison.py`
reconnaît.

---

## 7. Les dix critères du plan, un par un

| # | Critère | Verdict |
|---|---|---|
| 1 | Le tableau de l'étape 0 est publié, avec le coût d'oubli et le statut de chaque vérification | ✅ **tenu** — 19 lignes, dont 3 explicitement laissées à l'humain ou non décidables |
| 2 | Le job de disclosure tourne, son taux est publié, il est livré non bloquant avec la date à laquelle il le deviendra | ✅ **tenu** — 7/105 (7 %), bascule au **2026-10-01**, écrite dans le workflow et dans `CONTRIBUTING.md` |
| 3 | Un test échoue si `synthetic_manga_page` est sautée. **Ce test seul justifie le lot** | ✅ **tenu** — `tests/test_fixture_police.py`, 10 tests, dont un qui mesure l'encre réellement posée |
| 4 | La CI tourne sur Windows **et** Linux, et échoue si le nombre de tests collectés diffère | ⚠ **tenu au code, non vérifié en exécution** — voir « ce que la mesure ne dit pas », point 1 |
| 5 | Le nombre de tests annoncé est identique dans les trois fichiers, et un test le vérifie | ✅ **tenu** — 2 852 au 2026-08-28, et le test a été vu échouer sur la divergence |
| 6 | Un job refuse un diff contenant un poids, un fichier sous `sources/`/`build/`, ou un fichier de la liste noire | ✅ **tenu**, avec une nuance écrite : la liste noire ne s'arme qu'à `--index`, parce que `docs/PUBLICATION-ANGELITH.md` est légitimement suivi sur les branches de dev |
| 7 | Le tableau du banc apparaît dans le résumé de job, avec la mention de ce qu'il ne mesure pas | ✅ **tenu** |
| 8 | Un tag produit une release dont le corps est la section de CHANGELOG correspondante | ⚠ **tenu au code, non vérifié en exécution** — aucun tag n'a été posé ; voir point 2 |
| 9 | Chaque job a un `timeout-minutes` et une action épinglée par version | ✅ **tenu** — 10 jobs, 10 `timeout-minutes` ; toutes les actions portent une version explicite, aucune n'est sur `@main`. ⚠ Les actions officielles restent sur leur étiquette de MAJEUR (`checkout@v4`), les tierces sont épinglées au correctif (`sonarqube-scan-action@v8.2.1`, `action-gh-release@v2.0.8`), sauf `r-lib/actions/setup-pandoc@v2` qui l'était déjà ainsi avant ce lot — la distinction est celle qui existait déjà dans `ci.yml`, et sa raison y est écrite |
| 10 | `ruff check .` et la boucle courte passent, sur les deux OS | ⚠ **vérifié sur Windows seulement** — `ruff check .` passe, et la boucle courte rend 2 793 passés, 2 sautés, 57 désélectionnés en 11 min 34 s. Voir point 1 |

**Sept critères tenus, trois tenus au code mais non vérifiés en exécution** (4, 8 et 10 —
tous les trois pour la même raison : aucun workflow n'a tourné). Aucun n'est abandonné.

---

## 8. Ce que la mesure ne dit pas

1. **Rien de ce qui touche à GitHub Actions n'a été exécuté**, à une exception près : la
   commande de l'étape de résumé du banc, exercée en local (cf. §5). La matrice Linux, le job
   `collecte`, les quatre jobs de garde-fous, le workflow de publication et Dependabot sont
   écrits, leur YAML est validé (`yaml.safe_load` sur les cinq fichiers), et la logique qu'ils
   appellent est testée hors CI — mais **aucun run réel n'a eu lieu**. C'est la limite
   principale de ce document, et elle porte sur les critères 4, 8 et 10.

   Le risque nommé, par ordre de probabilité :
   - **Linux collecte moins de tests que Windows.** Aucun `importorskip` du dépôt ne dépend de
     l'OS — les 19 recensés portent tous sur un paquet — donc la collecte *devrait* coïncider.
     Si elle ne coïncide pas, le job `collecte` le dira, et c'est exactement son travail.
   - **PySide6 ne démarre pas sur l'image Ubuntu.** Quatre bibliothèques sont installées pour
     ça (`libegl1`, `libgl1`, `libxkbcommon-x11-0`, `libdbus-1-3`) ; la liste vient de la
     documentation de Qt, pas d'une mesure sur ce dépôt.
   - **Pandoc 3.1.11 via `r-lib/actions` sur Ubuntu** n'a jamais été exercé ici.

2. **Le taux de conformité de la disclosure porte sur l'historique, pas sur des PR.** Le job
   ne juge que les commits d'une PR ; le chiffre de 7 % mesure un passé qu'il ne jugera jamais.
   Ce que la bascule du 2026-10-01 doit regarder, c'est le taux **sur les PR ouvertes d'ici
   là** — et il n'y en a aucune aujourd'hui.

3. **Le couple de `ci.yml` (2 644 / 2 504) n'a pas été reproduit.** Il porte sa date du
   2026-08-27 et son arithmétique est vérifiée, mais personne n'a relancé une collecte sans
   PySide6 depuis. Il documente une mesure passée ; il ne prétend pas décrire l'état courant.

4. **Le banc n'a pas été relancé.** Ce lot ne touche ni au détecteur, ni aux seuils, ni à
   `config.yaml` — dont l'empreinte est inchangée. Le tableau de référence reste
   `docs/mesures/banc-2026-08-25.md`. Ce que le lot change au banc, c'est **où son résultat s'affiche**,
   pas ce qu'il mesure.

5. **Les 19 fichiers portant un titre d'œuvre ne sont pas corrigés.** Ils sont mesurés, listés
   et publiés à chaque PR ; leur nettoyage demande un jugement document par document et
   constitue un lot à part.

6. **Aucun run hebdomadaire n'a eu lieu**, par construction : le premier tombera le lundi
   suivant la fusion. On ne saura donc qu'alors si `pip install --upgrade onnxruntime numpy`
   fait bouger le rappel sur le corpus synthétique — c'est précisément la question que ce run
   existe pour poser.

7. **Aucune couverture de code n'est ajoutée, et c'est volontaire.** Un seuil de couverture sur
   un dépôt de 57 000 lignes dont la valeur est dans des mesures produirait des tests écrits
   pour le chiffre. Le projet a déjà une meilleure métrique — le banc — et elle mesure ce qui
   compte.

---

## 9. Ce que le lot ne fait pas

- **Aucun empaquetage, aucun installeur.** Jalon distinct de `docs/roadmap.md`, avec son propre
  périmètre. Ce lot livre le squelette — un job de release qui sait publier — pas l'artefact.
- **Aucune publication sur PyPI.** Le projet n'est pas empaqueté et ne veut pas l'être.
- **Aucun changement au pipeline ni à l'interface.** Aucun prompt, aucun seuil, aucune étape,
  aucun format de sortie, aucune clé de `config.yaml`, aucun cache invalidé,
  `checkpoints.FORMAT_VERSION` intact.
- **Aucun push automatique vers le miroir.** Cf. §6, et la raison est écrite.
